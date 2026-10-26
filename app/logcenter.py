import atexit
import http
import logging

from flask import current_app
from logcenter_sdk import (
    LogCenterConfig,
    LogCenterSender,
    LogCenterV3Config,
    LogCenterV3Sender,
)

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_STATUS_MESSAGE_OVERRIDES = {200: "success"}


def _status_message(status):
    """Converte um status HTTP (ex.: 404) na mensagem correspondente em snake_case
    (ex.: "not_found"). 200 vira "success" em vez de "ok"."""
    try:
        code = int(status)
    except (TypeError, ValueError):
        return str(status)

    if code in _STATUS_MESSAGE_OVERRIDES:
        return _STATUS_MESSAGE_OVERRIDES[code]
    try:
        return http.HTTPStatus(code).name.lower()
    except ValueError:
        return str(code)


def init_logcenter(app):
    """Cria e registra o LogCenterSender em app.extensions["logcenter"].

    Fica desabilitado (None) se LOGCENTER_ENABLED=false ou se faltar
    base_url/project_id, evitando criar a spool dir (.logcenter/) e a thread
    de retry em background à toa em dev/testes sem o LogCenter configurado.
    """
    base_url = app.config.get("LOGCENTER_BASE_URL")
    base_url_v3 = app.config.get("LOGCENTERV3_BASE_URL")
    project_id = app.config.get("LOGCENTER_PROJECT_ID")
    
    if app.config.get("LOGCENTERV3_ENABLED") and base_url_v3:
        cfgv3 = LogCenterV3Config(
            base_url=base_url_v3,
            api_key=app.config.get("LOGCENTERV3_API_KEY"),
            timeout_s=app.config["LOGCENTERV3_TIMEOUT_S"],
            spool_dir=app.config["LOGCENTERV3_SPOOL_DIR"],
            flush_interval_s=app.config["LOGCENTERV3_FLUSH_INTERVAL_S"],
            auto_flush=app.config["LOGCENTERV3_AUTO_FLUSH"],
            region_name=app.config["LOGCENTERV3_REGION_NAME"],
            aws_access_key_id=app.config["LOGCENTERV3_AWS_ACCESS_KEY"],
            aws_secret_access_key=app.config["LOGCENTERV3_AWS_SECRET_ACCESS_KEY"],
            log_group_name=app.config["LOGCENTERV3_LOG_GROUP"],
            log_stream_name=app.config["LOGCENTERV3_LOG_STREAM_NAME"],
        )
        print(app.config["LOGCENTERV3_REGION_NAME"])
        senderv3 = LogCenterV3Sender(cfgv3)
        app.extensions["logcenterv3"] = senderv3
        atexit.register(senderv3.stop_background_flush_thread)

    if not (app.config.get("LOGCENTER_ENABLED") and base_url and project_id):
        app.extensions["logcenter"] = None
        return None

    cfg = LogCenterConfig(
        base_url=base_url,
        project_id=project_id,
        api_key=app.config.get("LOGCENTER_API_KEY"),
        timeout_s=app.config["LOGCENTER_TIMEOUT_S"],
        spool_dir=app.config["LOGCENTER_SPOOL_DIR"],
        flush_interval_s=app.config["LOGCENTER_FLUSH_INTERVAL_S"],
        auto_flush=app.config["LOGCENTER_AUTO_FLUSH"],
    )

    sender = LogCenterSender(cfg)
    app.extensions["logcenter"] = sender
    atexit.register(sender.stop_background_flush_thread)
    return sender


def get_logcenter():
    """Retorna o LogCenterSender da app atual, ou None se estiver desabilitado."""
    return current_app.extensions.get("logcenter")


def get_logcenter_v3():
    """Retorna o LogCenterSender da app atual, ou None se estiver desabilitado."""
    return current_app.extensions.get("logcenterv3")


def log_event(level, message, *, data=None, status=None):
    """Envia um evento (DEBUG/INFO/ERROR/...) ao logger local e ao LogCenter.

    Tags sempre ["server", EVENT_LOCATION]. `status` carrega o status HTTP
    da requisição, quando aplicável.
    """
    level = level.upper()
    current_app.logger.log(_LEVELS.get(level, logging.INFO), message)

    sender = get_logcenter()
    if sender is None:
        return

    event_location = current_app.config.get("EVENT_LOCATION", "")
    tags = ["server", event_location]
    data = {**(data or {}), "event_location": event_location}
    sender.send_sync(
        level,
        message,
        tags=tags,
        data=data,
        status=_status_message(status) if status is not None else None,
    )


def log_event_v3(payload, isDebug: bool = False):
    senderv3 = get_logcenter_v3()
    if senderv3 is None:
        return
    if not isDebug:
        senderv3.send_sync(payload)
    else:
        senderv3.send_debug(payload)
