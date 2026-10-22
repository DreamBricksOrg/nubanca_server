from enum import Enum
from datetime import datetime, timezone
from copy import deepcopy
import uuid


class EventType(Enum):
    imprimir_imagem_sucesso = {
        "event_id": "",
        "event_type_id": 2,
        "occurred_at": "{datetime}",
        "data": {"file": "{file}"},
    }

    visualizar_foto_acessada = {
        "event_id": "",
        "event_type_id": 3,
        "occurred_at": "{datetime}",
        "data": {
            "ip": "{ip}",
            "browser": "{browser}",
            "filename": "{filename}",
            "platform": "{platform}",
            "user_agent": "{user_agent}",
        },
    }

    compartilhar_imagem = {
        "event_id": "",
        "event_type_id": 4,
        "occurred_at": "{datetime}",
        "data": {
            "ip": "{ip}",
            "browser": "{browser}",
            "filename": "{filename}",
            "platform": "{platform}",
            "user_agent": "{user_agent}",
        },
    }

    baixar_imagem = {
        "event_id": "",
        "event_type_id": 5,
        "occurred_at": "{datetime}",
        "data": {
            "ip": "{ip}",
            "browser": "{browser}",
            "filename": "{filename}",
            "platform": "{platform}",
            "user_agent": "{user_agent}",
        },
    }

    def generate_payload(self, data: dict | None = None) -> dict:
        payload = deepcopy(self.value)
        event_id = uuid.uuid4()
        payload["event_id"] = str(event_id)
        payload["occurred_at"] = datetime.now(timezone.utc).isoformat()
        print(data.keys())
        if data is not None:
            allowed_fields = payload["data"].keys()
            invalid_fields = data.keys() - allowed_fields

            if invalid_fields:
                raise ValueError(
                    f"Invalid data fields for {self.name}: {invalid_fields}"
                )

            payload["data"].update(data)
        elif payload["data"]:
            allowed_fields = payload["data"].keys()
            raise ValueError(f"Data field must receive values {self.name}: {allowed_fields}")
            return

        return payload
