from bisect import bisect_left
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone

from bson import ObjectId
from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, current_app, render_template, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from . import s3_storage

bp = Blueprint("reports", __name__)
PRINT = "imprimir_imagem_sucesso"
QR_ONLY = "apenas_qrcode_gerado"
REPRINT = "reimprimir_imagem_sucesso"
VIEW = "visualizar_foto_acessada"
EVENTS = (
    (PRINT, "Geradas para impressão"),
    (QR_ONLY, "Apenas QR Code"),
    (REPRINT, "Reimpressões"),
    (VIEW, "Visualizações"),
    ("compartilhar_imagem", "Compartilhamentos"),
    ("baixar_imagem", "Downloads"),
)
LOCATIONS = ("sp", "rj")
BRASILIA = timezone(timedelta(hours=-3))


def _period(start, end):
    start_at = datetime.combine(start, time.min, tzinfo=BRASILIA).astimezone(timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=BRASILIA).astimezone(timezone.utc)
    return start_at, end_at


def _dates():
    today = datetime.now(BRASILIA).date()
    try:
        start = date.fromisoformat(request.args.get("inicio", (today - timedelta(days=6)).isoformat()))
        end = date.fromisoformat(request.args.get("fim", today.isoformat()))
    except ValueError:
        return None
    if start > end or (end - start).days > 30:
        return None
    return start, end


def _event_time(value):
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(moment, datetime):
            return None
        return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)
    except ValueError:
        return None


def _quick_access_counts(collection, project_id, location, start, end):
    start_at, end_at = _period(start, end)
    after_end = end_at + timedelta(minutes=1)
    query = {
        "project_id": project_id,
        "data.event_location": location,
        "message": {"$in": (PRINT, QR_ONLY, VIEW)},
        "$or": [
            {"timestamp": {"$gte": start_at.date().isoformat(),
                           "$lt": (after_end.date() + timedelta(days=1)).isoformat()}},
            {"timestamp": {"$gte": start_at, "$lt": after_end}},
        ],
    }
    views = {}
    generated = []
    for record in collection.find(query, {"_id": 0, "message": 1, "timestamp": 1,
                                          "data.file": 1, "data.filename": 1}):
        moment = _event_time(record.get("timestamp"))
        data = record.get("data")
        if moment is None or not isinstance(data, dict):
            continue
        if record["message"] == VIEW:
            filename = data.get("filename")
            if isinstance(filename, str) and filename and start_at <= moment < after_end:
                views.setdefault(filename, []).append(moment)
        else:
            filename = data.get("file")
            if isinstance(filename, str) and filename and start_at <= moment < end_at:
                generated.append((moment, record["message"], filename))

    for times in views.values():
        times.sort()
    counts = {}
    seen = set()
    for moment, message, filename in sorted(generated):
        key = (message, filename)
        if key in seen:
            continue
        seen.add(key)
        times = views.get(filename, [])
        index = bisect_left(times, moment)
        if index < len(times) and times[index] <= moment + timedelta(minutes=1):
            day = moment.astimezone(BRASILIA).date().isoformat()
            counts.setdefault(day, {PRINT: 0, QR_ONLY: 0})[message] += 1
    return counts


def _removed_count(collection, project_id, location, start, end):
    start_at, end_at = _period(start, end)
    query = {"project_id": project_id, "data.event_location": location,
             "message": {"$in": (PRINT, QR_ONLY)},
             "$or": [
                 {"timestamp": {"$gte": start_at.date().isoformat(),
                                "$lt": (end_at.date() + timedelta(days=1)).isoformat()}},
                 {"timestamp": {"$gte": start_at, "$lt": end_at}},
             ]}
    filenames = set()
    unknown = False
    for record in collection.find(query, {"_id": 0, "timestamp": 1, "data.file": 1}):
        occurred = _event_time(record.get("timestamp"))
        if occurred is None or not start_at <= occurred < end_at:
            continue
        data = record.get("data")
        filename = data.get("file") if isinstance(data, dict) else None
        if isinstance(filename, str) and filename:
            filenames.add(filename)
        else:
            unknown = True
    if unknown:
        return None
    if not filenames:
        return 0
    existing = s3_storage.list_back_cover_keys(location)
    return sum(f"back-covers/{location}/{filename}" not in existing for filename in filenames)


def _daily_counts(start, end, location):
    config = current_app.config
    project_id = ObjectId(config["LOGCENTER_PROJECT_ID"])
    client = MongoClient(config["LOGCENTER_MONGOURL"], serverSelectionTimeoutMS=3000,
                         connectTimeoutMS=3000, socketTimeoutMS=5000)
    try:
        database = client[config["LOGCENTER_MONGO_DB"]] if config["LOGCENTER_MONGO_DB"] else client.get_default_database()
        collection = database[config["LOGCENTER_MONGO_COLLECTION"]]
        events = {"$in": [message for message, _ in EVENTS]}
        start_at, end_at = _period(start, end)
        query = {"project_id": project_id, "data.event_location": location, "message": events,
                 "$or": [
                     {"timestamp": {"$gte": start_at.date().isoformat(),
                                    "$lt": (end_at.date() + timedelta(days=1)).isoformat()}},
                     {"timestamp": {"$gte": start_at, "$lt": end_at}},
                 ]}
        by_day = Counter()
        by_hour = Counter()
        for record in collection.find(query, {"_id": 0, "message": 1, "timestamp": 1}):
            occurred = _event_time(record.get("timestamp"))
            if occurred is not None and start_at <= occurred < end_at:
                local = occurred.astimezone(BRASILIA)
                event = record["message"]
                by_day[(local.date().isoformat(), event)] += 1
                if event in (PRINT, QR_ONLY) and 10 <= local.hour <= 23:
                    by_hour[(local.hour, event)] += 1
        counts = [{"_id": {"day": day, "event": event}, "count": count}
                  for (day, event), count in by_day.items()]
        return (counts, _quick_access_counts(collection, project_id, location, start, end),
                by_hour, _removed_count(collection, project_id, location, start, end))
    finally:
        client.close()


@bp.get("/relatorio")
def report_page():
    dates = _dates()
    if dates is None:
        return "Período inválido: use datas ISO e até 31 dias.", 400
    location = request.args.get("event_location", current_app.config["EVENT_LOCATION"] or "sp")
    if location not in LOCATIONS:
        return "Local inválido: escolha sp ou rj.", 400
    if not current_app.config["LOGCENTER_MONGOURL"] or not current_app.config["LOGCENTER_PROJECT_ID"]:
        return "Falta configuração do MongoDB ou projeto do LogCenter.", 503
    start, end = dates
    try:
        counts, quick_access, by_hour, removed_count = _daily_counts(start, end, location)
    except (PyMongoError, BotoCoreError, ClientError, ValueError, TypeError) as exc:
        current_app.logger.warning("Falha ao consultar relatório do LogCenter: %s", type(exc).__name__)
        return "Não foi possível consultar o LogCenter. Verifique a conexão e o banco configurado.", 503

    days = []
    current = start
    while current <= end:
        day = current.isoformat()
        days.append({"date": day, "counts": {event_id: 0 for event_id, _ in EVENTS},
                     "printed_opened": quick_access.get(day, {}).get(PRINT, 0),
                     "digital_opened": quick_access.get(day, {}).get(QR_ONLY, 0)})
        current += timedelta(days=1)
    by_date = {day["date"]: day for day in days}
    for row in counts:
        day = by_date.get(row["_id"]["day"])
        event_id = row["_id"]["event"]
        if day is not None and event_id in day["counts"]:
            day["counts"][event_id] += row["count"]
    for day in days:
        day["generated"] = day["counts"][PRINT] + day["counts"][QR_ONLY]
    totals = {event_id: sum(day["counts"][event_id] for day in days) for event_id, _ in EVENTS}
    generated_total = totals[PRINT] + totals[QR_ONLY]
    hourly = [{"hour": hour, "printed": by_hour[(hour, PRINT)], "digital": by_hour[(hour, QR_ONLY)],
               "total": by_hour[(hour, PRINT)] + by_hour[(hour, QR_ONLY)]} for hour in range(10, 24)]
    busiest = max(hourly, key=lambda row: row["total"])
    max_hourly = max(busiest["total"], 1)
    for row in hourly:
        row["printed_percent"] = max(1, round(100 * row["printed"] / max_hourly)) if row["printed"] else 0
        row["digital_percent"] = max(1, round(100 * row["digital"] / max_hourly)) if row["digital"] else 0
    outside_hours = generated_total - sum(row["total"] for row in hourly)
    daily_chart = [{"date": day["date"], "label": day["date"][8:10] + "/" + day["date"][5:7],
                    "printed": day["counts"][PRINT], "digital": day["counts"][QR_ONLY],
                    "total": day["generated"]} for day in days]
    busiest_day = max(daily_chart, key=lambda row: row["total"])
    max_daily = max(busiest_day["total"], 1)
    for row in daily_chart:
        row["printed_percent"] = max(1, round(100 * row["printed"] / max_daily)) if row["printed"] else 0
        row["digital_percent"] = max(1, round(100 * row["digital"] / max_daily)) if row["digital"] else 0
    response = current_app.make_response(render_template("reports.html", start=start.isoformat(), end=end.isoformat(),
                                                        location=location, events=EVENTS, totals=totals, days=days,
                                                        generated_total=generated_total, hourly=hourly,
                                                        removed_count=removed_count,
                                                        busiest=busiest if busiest["total"] else None,
                                                        outside_hours=outside_hours, daily_chart=daily_chart,
                                                        busiest_day=busiest_day if busiest_day["total"] else None,
                                                        daily_chart_width=max(720, len(days) * 42)))
    response.headers["Cache-Control"] = "no-store"
    return response
