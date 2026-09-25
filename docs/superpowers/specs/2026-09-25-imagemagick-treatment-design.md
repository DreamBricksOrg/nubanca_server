# Tratamento de imagem via ImageMagick em /image — Design

Date: 2026-09-25

## Contexto

`GET /image` (`app/routes.py:get_image`) promove a captura mais recente de `storage/captures/` para `storage/photos/` via `storage.promote_latest_capture` e retorna a URL pública da foto. Ainda não existe nenhum tratamento de imagem nesse fluxo.

Queremos deixar a integração com a ferramenta de linha de comando ImageMagick configurada e funcionando de ponta a ponta, mesmo sem saber ainda qual tratamento (correção de cor, crop, watermark, etc.) será aplicado. O objetivo desta etapa é puramente de infraestrutura: um comando ImageMagick real roda sobre a foto promovida, os argumentos vêm de configuração, e o resultado (sucesso ou falha) é tratado sem quebrar `/image`. O tratamento em si é preenchido depois, trocando apenas `IMAGEMAGICK_ARGS`.

## Decisões de escopo

- **Hook point:** dentro de `get_image()`, logo após `storage.promote_latest_capture` mover o arquivo para `photos/` e antes de montar a `image_url`. Roda em toda chamada de `/image` que promove uma captura nova.
- **Comportamento inicial:** no-op configurável. Sem `IMAGEMAGICK_ARGS` definido, o comando executado é `magick <path> <path>` — um round-trip real pelo ImageMagick (decodifica e recodifica a imagem) que não altera o conteúdo visualmente, só prova que a integração funciona.
- **Tratamento em disco, in-place:** o mesmo arquivo em `photos/` é lido e sobrescrito (`magick origem [args] destino` com origem == destino). Não cria uma cópia paralela nem exige limpeza extra.
- **Falha é não-fatal:** se o binário não existir, o comando retornar código diferente de zero, ou estourar timeout, o erro é logado e `/image` segue normalmente, servindo a foto como está (sem o tratamento). Mesmo padrão que `POST /print` já usa para `PrintError`.
- **Configuração segue o padrão de `PRINT_*`:** habilitar/desabilitar, caminho do binário, argumentos e timeout todos vêm de env vars com defaults sãos.

## Arquitetura

```
app/
├── imagemagick.py   # NOVO: TreatmentError, apply_treatment(path)
├── routes.py        # get_image() chama imagemagick.apply_treatment(dest) após promover
└── config.py        # + IMAGEMAGICK_ENABLED, IMAGEMAGICK_PATH, IMAGEMAGICK_ARGS, IMAGEMAGICK_TIMEOUT
```

`app/imagemagick.py` é independente de `app/printing.py` (ferramentas e domínios diferentes: tratamento de imagem vs. impressão), mas segue a mesma forma — módulo fino, uma exceção própria, config lida via `current_app.config` no momento da chamada.

## Módulo `app/imagemagick.py`

```python
import logging
import shlex
import subprocess
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)


class TreatmentError(Exception):
    """Raised when the ImageMagick treatment command fails."""


def apply_treatment(path: Path) -> dict:
    config = current_app.config
    if not config.get("IMAGEMAGICK_ENABLED", True):
        logger.info("Tratamento ImageMagick desabilitado via IMAGEMAGICK_ENABLED; ignorando: %s", path)
        return {"treated": False, "message": "Tratamento desabilitado"}

    magick_path = config["IMAGEMAGICK_PATH"]
    extra_args = shlex.split(config.get("IMAGEMAGICK_ARGS") or "")
    timeout = config.get("IMAGEMAGICK_TIMEOUT", 60)

    args = [magick_path, str(path), *extra_args, str(path)]

    try:
        subprocess.run(args, check=True, timeout=timeout, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise TreatmentError(f"ImageMagick não encontrado em '{magick_path}'") from exc
    except subprocess.TimeoutExpired as exc:
        raise TreatmentError(f"Tratamento excedeu o tempo limite de {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = f"ImageMagick retornou código {exc.returncode}"
        if detail:
            message += f": {detail}"
        raise TreatmentError(message) from exc

    logger.info("Imagem tratada com sucesso via ImageMagick: %s", path)
    return {"treated": True, "message": "Imagem tratada com sucesso"}
```

Notas:
- `shlex.split` permite que `IMAGEMAGICK_ARGS` seja uma string simples no `.env` (ex.: `-auto-orient -strip`) e vire uma lista de argumentos, do mesmo jeito que `PRINT_SETTINGS` já é uma string simples hoje.
- Origem e destino no comando são o mesmo `path`: com `IMAGEMAGICK_ARGS` vazio isso é `magick foo.jpg foo.jpg`, uma recodificação real da imagem.

## Mudança em `app/routes.py`

```python
from . import imagemagick, printing, s3_storage, storage

@bp.get("/image")
def get_image():
    ...
    root = current_app.config["STORAGE_ROOT"]
    dest = storage.promote_latest_capture(root / "captures", root / "photos")
    if dest is None:
        return jsonify({"success": False, "message": "Nenhuma imagem nova disponível"}), 404

    try:
        imagemagick.apply_treatment(dest)
    except imagemagick.TreatmentError as exc:
        current_app.logger.error("Falha ao tratar imagem %s: %s", dest, exc)

    base_url = current_app.config["BASE_URL"].rstrip("/")
    image_url = f"{base_url}/files/photos/{dest.name}"
    return jsonify({"image_url": image_url})
```

## Config (`app/config.py` + `.env.example`)

```python
IMAGEMAGICK_ENABLED = os.environ.get("IMAGEMAGICK_ENABLED", "true").strip().lower() not in ("false", "0", "")
IMAGEMAGICK_PATH = os.environ.get("IMAGEMAGICK_PATH", "magick")
IMAGEMAGICK_ARGS = os.environ.get("IMAGEMAGICK_ARGS", "")
IMAGEMAGICK_TIMEOUT = int(os.environ.get("IMAGEMAGICK_TIMEOUT", "60"))
```

`.env.example` ganha essas 4 linhas, próximas às de `PRINT_*`.

## Testes

- `tests/test_imagemagick.py` (novo, espelha `tests/test_printing.py`):
  - roda o comando esperado (`magick <path> <path>`) quando `IMAGEMAGICK_ARGS` está vazio, via `monkeypatch.setattr(subprocess, "run", ...)`;
  - inclui os argumentos extras (com `shlex.split`) quando `IMAGEMAGICK_ARGS` está configurado;
  - retorna `{"treated": False, ...}` sem chamar `subprocess.run` quando `IMAGEMAGICK_ENABLED=False`;
  - levanta `TreatmentError` para binário ausente (`FileNotFoundError`), código de saída != 0 (`CalledProcessError`, mensagem inclui `stderr`) e timeout (`TimeoutExpired`).
- `tests/test_config.py`: novo teste de defaults sãos para `IMAGEMAGICK_ENABLED` (`True`), `IMAGEMAGICK_PATH` (`"magick"`), `IMAGEMAGICK_ARGS` (`""`), `IMAGEMAGICK_TIMEOUT` (`60`).
- `tests/conftest.py`: `TestConfig` ganha `IMAGEMAGICK_ENABLED = False`, para que os testes de `/image` existentes (que usam bytes falsos como se fossem `.jpg`) não tentem invocar um binário `magick` de verdade.
- `tests/test_routes.py`: novo teste `test_get_image_calls_imagemagick_treatment`, no mesmo espírito de `test_post_print_calls_print_image` — habilita `IMAGEMAGICK_ENABLED` nesse teste, monkeypatcha `app.routes.imagemagick.apply_treatment` para registrar a chamada, e confirma que `/image` continua retornando 200 mesmo quando o fake levanta `TreatmentError`.

## Erros e casos de borda

- Timeout, binário ausente e erro de execução resultam no mesmo comportamento observável: log de erro e a foto original (sem tratamento) é servida normalmente — consistente com a decisão de que o tratamento nunca deve bloquear a captura.
- `IMAGEMAGICK_ARGS` mal formado para `shlex.split` (ex.: aspas desbalanceadas) levantaria `ValueError` fora do `try/except` atual de `apply_treatment`; como isso só pode acontecer por erro de configuração (não por dado de usuário), fica deliberadamente sem tratamento especial nesta fase — quebra alto e claro no log, e é resolvido ajustando o `.env`.
