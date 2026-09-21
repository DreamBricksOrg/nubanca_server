# Photo Print API — Design

Date: 2026-09-21

## Context

Fluxo de um projeto de fotos: uma câmera Sony captura imagens e as grava em uma pasta do servidor (`captures`). Uma aplicação Flask expõe endpoints para que:

1. Um tablet (com outra aplicação, responsável pela colagem/tratamento visual) faça polling em busca de imagens novas, receba a foto crua e, depois de tratá-la, envie o resultado final de volta.
2. A imagem final tratada seja salva e impressa em papel A4.

O hardware (câmera e impressora) ainda não está disponível para testes end-to-end nesta fase; o comando real de impressão via PowerShell fica como stub.

## Arquitetura

Flask app factory (`create_app()`) com estrutura modular:

```
nubanca-server/
├── app/
│   ├── __init__.py       # create_app(), registra blueprint, cria pastas
│   ├── config.py         # STORAGE_ROOT, HOST, PORT, BASE_URL (via .env)
│   ├── storage.py        # lógica de pastas: listar, mover, renomear arquivos
│   ├── printing.py       # stub do comando PowerShell de impressão
│   └── routes.py         # blueprint com /image, /discard, /print, /files/<...>
├── storage/
│   ├── captures/
│   ├── photos/
│   ├── discards/
│   └── back-covers/
├── run.py                # entrypoint (flask run / python run.py)
├── requirements.txt
├── .env.example
└── tests/
    └── test_routes.py    # pytest com tmp_path substituindo STORAGE_ROOT
```

`STORAGE_ROOT` é configurável via `.env` (default: `./storage`). `BASE_URL` (default `http://<HOST>:<PORT>`) é usado para montar `image_url` nas respostas.

## Endpoints

### `GET /image`

Faz o "poll" da pasta `captures/`:

- Se `captures/` estiver vazia → `204 No Content` (sem corpo).
- Se houver um ou mais arquivos: seleciona o **mais recente** por mtime, renomeia para timestamp (`YYYYMMDD_HHMMSS.<ext>`, com sufixo `_1`, `_2`... em caso de colisão) e move para `photos/`. Os demais arquivos encontrados em `captures/` (mais antigos) são **apagados**.
- Retorna `200 {"image_url": "<BASE_URL>/files/photos/<nome>"}`.

### `POST /discard`

Sem corpo esperado.

- Localiza o arquivo mais recente (mtime) em `photos/`.
- Se não houver nenhum → `404 {"success": false, "message": "Nenhuma foto para descartar"}`.
- Move o arquivo (mantendo o nome) para `discards/`.
- Sucesso → `200 {"success": true, "message": "Foto descartada"}`.

### `POST /print`

`multipart/form-data` com campo `image` (arquivo — a imagem final já tratada/colada pelo tablet).

- Valida presença do arquivo e extensão permitida (`.jpg`, `.jpeg`, `.png`); inválido → `400 {"success": false, "message": "..."}`.
- Salva em `back-covers/` com nome timestamp (mesma lógica de colisão do `/image`).
- Chama `printing.print_image(path)` — função stub que loga a chamada e retorna um resultado indicando que a impressão real ainda não está implementada. A assinatura já é pensada para receber futuramente um `subprocess.run(["powershell", "-Command", ...])` real.
- Retorna `200 {"success": true, "message": "Imagem salva em back-covers; impressão ainda não implementada (stub)"}` (o `success` reflete o salvamento do arquivo, não a impressão física).

### `GET /files/<folder>/<filename>`

Serve arquivos estáticos apenas das 4 pastas conhecidas (`captures`, `photos`, `discards`, `back-covers`, allowlist explícita). Qualquer outro valor de `folder` → `404`. Usado para montar as URLs retornadas por `/image`.

## Validação e tratamento de erros

- Extensões de imagem permitidas: `.jpg`, `.jpeg`, `.png`.
- As 4 pastas de `storage/` são criadas automaticamente no startup da aplicação, se não existirem.
- `/files/<folder>/<filename>` usa allowlist de pastas e `secure_filename`/checagem de path para evitar path traversal.
- Sem hardware real disponível: `/print` usa stub de impressão; os testes automatizados usam `pytest` com `tmp_path` substituindo `STORAGE_ROOT`, sem depender de arquivos de câmera reais.

## Testes

- `pytest` cobrindo:
  - `/image`: pasta vazia → 204; um arquivo → move e renomeia, retorna URL; múltiplos arquivos → mantém só o mais recente em `photos/`, apaga os outros de `captures/`.
  - `/discard`: `photos/` vazia → 404; com arquivo → move para `discards/`.
  - `/print`: upload válido → salva em `back-covers/`, chama stub de impressão, retorna sucesso; extensão inválida → 400.
  - `/files/<folder>/<filename>`: pasta fora da allowlist → 404.
- Fixture de teste substitui `STORAGE_ROOT` por `tmp_path`, evitando tocar o filesystem real do projeto.
