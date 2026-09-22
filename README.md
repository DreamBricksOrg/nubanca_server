# Nubanca Server

API Flask para o fluxo de captura e impressão de fotos: uma câmera Sony grava a foto capturada no servidor, um tablet faz o tratamento/colagem da imagem através desta API, e a imagem final é impressa em papel A4.

## Fluxo

1. A câmera salva a foto capturada em `storage/captures/`.
2. O tablet faz polling em `GET /image`. Quando há uma foto nova, ela é movida para `storage/photos/` e sua URL é retornada.
3. O tablet pode descartar a foto (`POST /discard`) ou tratá-la (colagem) e enviar o resultado final (`POST /print`), que salva a imagem em `storage/back-covers/` e aciona a impressão.

```
storage/
├── captures/     # fotos cruas da câmera (entrada)
├── photos/       # fotos promovidas, aguardando tratamento no tablet
├── discards/     # fotos descartadas
└── back-covers/  # imagens finais tratadas, prontas para impressão
```

## Como rodar

### 1. Pré-requisitos

- Python 3.12+
- Windows (o passo de impressão via PowerShell, quando implementado, depende disso)

### 2. Instalar dependências

```bash
python -m venv venv
source venv/Scripts/activate   # Windows (git-bash) — no cmd/PowerShell use venv\Scripts\activate
pip install -r requirements-dev.txt   # inclui pytest; use requirements.txt para produção
```

### 3. Configurar variáveis de ambiente (opcional)

Copie `.env.example` para `.env` e ajuste se necessário:

```
STORAGE_ROOT=storage       # pasta raiz onde captures/photos/discards/back-covers são criadas
HOST=0.0.0.0
PORT=5000
BASE_URL=http://localhost:5000   # usado para montar as URLs retornadas por /image
```

As 4 subpastas de `STORAGE_ROOT` são criadas automaticamente ao iniciar o servidor, se não existirem.

### 4. Rodar o servidor

```bash
python run.py
```

O servidor sobe em `http://<HOST>:<PORT>` (por padrão `http://localhost:5000`).

### 5. Rodar os testes

```bash
pytest
```

## Documentação interativa (Swagger)

Com o servidor rodando, a documentação interativa dos endpoints está disponível em:

- **UI:** `http://localhost:5000/docs/`
- **Spec OpenAPI (JSON):** `http://localhost:5000/apispec.json`

## Endpoints

Todas as respostas são JSON, exceto `GET /files/<folder>/<filename>`, que retorna o arquivo de imagem bruto.

### `GET /image`

Faz o polling da pasta `captures/`. Se houver uma foto nova, promove a mais recente para `photos/` (renomeando para um timestamp) e apaga quaisquer outras fotos que estejam em `captures/` no momento.

| Status | Corpo | Quando |
|---|---|---|
| `200` | `{"image_url": "http://localhost:5000/files/photos/20260921_143201.jpg"}` | Havia uma foto nova; ela foi promovida e sua URL é retornada. |
| `404` | `{"success": false, "message": "Nenhuma imagem nova disponível"}` | Não há foto nova em `captures/`. |

### `POST /discard`

Descarta a foto mais recente de `photos/`, movendo-a para `discards/`. Não recebe parâmetros — sempre age sobre a foto mais recente.

| Status | Corpo | Quando |
|---|---|---|
| `200` | `{"success": true, "message": "Foto descartada"}` | A foto mais recente foi movida para `discards/`. |
| `404` | `{"success": false, "message": "Nenhuma foto para descartar"}` | Não há nenhuma foto em `photos/`. |

### `POST /print`

Recebe a imagem final tratada (colagem feita pelo tablet) como upload `multipart/form-data`, salva em `back-covers/` e aciona a impressão.

**Parâmetros (form-data):**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `image` | arquivo | sim | Imagem final (`.jpg`, `.jpeg` ou `.png`). |

| Status | Corpo | Quando |
|---|---|---|
| `200` | `{"success": true, "message": "Imagem salva em back-covers; impressão ainda não implementada (stub)"}` | Arquivo salvo com sucesso. |
| `400` | `{"success": false, "message": "..."}` | Nenhum arquivo enviado, ou extensão não permitida. |

> **Nota:** o comando real de impressão via PowerShell ainda não foi implementado — depende da definição da impressora/driver A4. Ver `app/printing.py` para o stub e o comentário indicando o que substituir.

Exemplo com `curl`:

```bash
curl -X POST http://localhost:5000/print -F "image=@collage.jpg"
```

### `GET /files/<folder>/<filename>`

Serve um arquivo salvo em uma das 4 pastas de armazenamento. `<folder>` deve ser exatamente `captures`, `photos`, `discards` ou `back-covers` — qualquer outro valor retorna `404`.

| Status | Quando |
|---|---|
| `200` | Arquivo encontrado; retorna o conteúdo da imagem. |
| `404` | Pasta fora da lista permitida, ou arquivo não existe. |

## Extensões de arquivo permitidas

`.jpg`, `.jpeg`, `.png` — qualquer outra extensão é rejeitada com `400` (em `/print`) ou ignorada (nas demais operações que listam arquivos).
