# Nubanca Server

API Flask para o fluxo de captura e impressão de fotos: uma câmera Sony grava a foto capturada no servidor, um tablet faz o tratamento/colagem da imagem através desta API, e a imagem final é impressa em papel A4.

## Fluxo

1. A câmera salva a foto capturada em `storage/captures/`.
2. O tablet faz polling em `GET /image`. Quando há uma foto nova, ela é movida para `storage/photos/` e sua URL é retornada.
3. O tablet pode descartar a foto (`POST /discard`) ou tratá-la (colagem) e enviar o resultado final (`POST /print`), que envia a imagem para o bucket S3 (prefixo `back-covers/`) e aciona a impressão.

```
storage/
├── captures/     # fotos cruas da câmera (entrada)
├── photos/       # fotos promovidas, aguardando tratamento no tablet
└── discards/     # fotos descartadas
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

### 3. Configurar variáveis de ambiente

Copie `.env.example` para `.env` e ajuste se necessário:

As variáveis `STORAGE_ROOT`, `HOST`, `PORT` e `BASE_URL` têm defaults razoáveis; as variáveis `AWS_*` são **obrigatórias** para `POST /print` e `GET /view/<filename>` funcionarem, já que a imagem final é enviada e servida via S3.

```
STORAGE_ROOT=storage       # pasta raiz onde captures/photos/discards são criadas
HOST=0.0.0.0
PORT=5000
BASE_URL=http://localhost:5000   # usado para montar as URLs retornadas por /image
AWS_ACCESS_KEY_ID=               # credenciais AWS usadas para enviar back-covers ao S3
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
AWS_S3_BUCKET=                   # bucket onde back-covers/<arquivo> é salvo
S3_PRESIGNED_URL_EXPIRES=86400   # validade (segundos) das URLs presigned usadas em /view
```

As 3 subpastas de `STORAGE_ROOT` são criadas automaticamente ao iniciar o servidor, se não existirem. `back-covers` não é mais uma pasta local — as imagens finais vão direto para o S3.

**Importante — CORS do bucket:** o botão "Compartilhar" na página `/view/<filename>` faz um `fetch()` client-side na URL presignada do S3 para montar um arquivo compartilhável (via `navigator.share`). Esse `fetch()` é cross-origin (o navegador está no domínio do app, a imagem está no domínio do S3), então o bucket **precisa de uma configuração de CORS** permitindo `GET` a partir da origem do app (ou `*`), senão o `fetch()` falha silenciosamente e o botão cai para compartilhar apenas o link, sem anexar a foto. Exemplo mínimo de CORS config do bucket (S3 console → bucket → Permissions → CORS):

```json
[
  {
    "AllowedOrigins": ["https://seu-dominio-do-app.com"],
    "AllowedMethods": ["GET"],
    "AllowedHeaders": ["*"]
  }
]
```

O botão DOWNLOAD e a exibição da foto (`<img>`) não dependem de CORS — funcionam normalmente mesmo sem essa configuração.

### 4. Rodar o servidor

```bash
python run.py
```

O servidor sobe em `http://<HOST>:<PORT>` (por padrão `http://localhost:5000`).

### 5. Rodar os testes

```bash
pytest
```

Os testes usam `moto` para mockar o S3 — não fazem chamadas reais à AWS, nem exigem credenciais configuradas.

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

Recebe a imagem final tratada (colagem feita pelo tablet) como upload `multipart/form-data`, envia para o bucket S3 (prefixo `back-covers/`) e aciona a impressão.

**Parâmetros (form-data):**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `image` | arquivo | sim | Imagem final (`.jpg`, `.jpeg` ou `.png`). |

| Status | Corpo | Quando |
|---|---|---|
| `200` | `{"success": true, "message": "...", "page_url": "http://localhost:5000/view/20260922_143201.jpg"}` | Arquivo salvo com sucesso. `page_url` aponta para a página de visualização/compartilhamento (ver `GET /view/<filename>`). |
| `400` | `{"success": false, "message": "..."}` | Nenhum arquivo enviado, ou extensão não permitida. |

> **Nota:** o comando real de impressão via PowerShell ainda não foi implementado — depende da definição da impressora/driver A4. Ver `app/printing.py` para o stub e o comentário indicando o que substituir.

Exemplo com `curl`:

```bash
curl -X POST http://localhost:5000/print -F "image=@collage.jpg"
```

### `GET /view/<filename>`

Página HTML (não JSON) para o cliente final ver a foto impressa no celular, com botões de **Compartilhar** (via `navigator.share` do navegador) e **Download**. `<filename>` é o nome do objeto salvo no S3 sob o prefixo `back-covers/` (normalmente obtido do `page_url` retornado por `POST /print`). A imagem em si é servida via presigned URL do S3 — a página faz um `head_object` no S3 para confirmar que o arquivo existe antes de renderizar.

Mostra uma splashscreen com a animação do logo (roxo/branco, seguindo o brand guideline da Nubank) enquanto a página e a foto carregam, evitando qualquer flash de conteúdo sem estilo.

| Status | Quando |
|---|---|
| `200` | Retorna a página HTML. |
| `404` | Não existe objeto com essa chave em `back-covers/` no S3. |

### `GET /files/<folder>/<filename>`

Serve um arquivo salvo em uma das 3 pastas de armazenamento local. `<folder>` deve ser exatamente `captures`, `photos` ou `discards` — qualquer outro valor (incluindo `back-covers`, que agora vive no S3, não em disco) retorna `404`.

| Status | Quando |
|---|---|
| `200` | Arquivo encontrado; retorna o conteúdo da imagem. |
| `404` | Pasta fora da lista permitida, ou arquivo não existe. |

## Extensões de arquivo permitidas

`.jpg`, `.jpeg`, `.png` — qualquer outra extensão é rejeitada com `400` (em `/print`) ou ignorada (nas demais operações que listam arquivos).
