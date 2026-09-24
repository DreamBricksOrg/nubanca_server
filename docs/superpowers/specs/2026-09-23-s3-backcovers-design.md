# Back-covers via S3 Presigned URL — Design

Date: 2026-09-23

## Context

Hoje `POST /print` salva a imagem final (back-cover) em disco, em `storage/back-covers/`, e `GET /view/<filename>` serve essa imagem (e o download) através de `GET /files/back-covers/<filename>`, direto do disco local do servidor.

Queremos que as imagens de `back-covers` passem a ser fornecidas em `/view` através de presigned URLs do S3, em vez de serem servidas pelo próprio Flask a partir do disco. `captures`, `photos` e `discards` continuam funcionando exatamente como hoje (disco local) — essa mudança é restrita a `back-covers`.

## Decisões de escopo

- **Só S3, sem dual-write:** `back-covers` deixa de ser uma pasta local persistente. `POST /print` não salva mais o arquivo final em `storage/back-covers/`; ele é enviado direto para o bucket S3.
- **Credenciais via `.env`:** `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` / `AWS_S3_BUCKET`, lidas como o resto da config atual (`os.environ`).
- **Expiração da presigned URL:** 24 horas (86400s), configurável via `.env`.
- **Existência do arquivo:** `GET /view/<filename>` faz um `head_object` no S3 antes de renderizar a página; se não existir, `404` (mesmo comportamento observável de hoje).
- **Download forçado:** o botão DOWNLOAD usa uma presigned URL separada, gerada com `ResponseContentDisposition=attachment; filename="..."`, para garantir que o navegador baixe o arquivo (o atributo HTML `download` não é confiável em link cross-origin para o S3).
- **Impressão continua recebendo um `Path` local:** `POST /print` grava a imagem num arquivo temporário antes de chamar `printing.print_image(temp_path)` (assinatura não muda), depois envia esse mesmo arquivo temporário para o S3 e apaga o temporário. Isso preserva a implementação futura da impressão via PowerShell, que precisa de um caminho de arquivo real.

## Arquitetura

```
app/
├── s3_storage.py         # NOVO: cliente boto3, upload, head_object, presigned URLs
├── storage.py            # FOLDERS perde "back-covers"; nova geração de nome único
│                          # sem depender de disco; novo helper de arquivo temporário
├── routes.py             # POST /print e GET /view/<filename> passam a falar com S3
├── config.py             # + AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
│                          #   AWS_S3_BUCKET, S3_PRESIGNED_URL_EXPIRES
└── templates/view.html   # botão DOWNLOAD usa download_url (não mais image_url)
```

`captures`, `photos`, `discards` continuam em `FOLDERS` e servidos por `GET /files/<folder>/<filename>` exatamente como hoje. `back-covers` sai desse allowlist — `GET /files/back-covers/<filename>` passa a 404 automaticamente (comportamento herdado do allowlist existente, sem precisar de código novo nessa rota).

## Módulo `app/s3_storage.py`

Três funções, usando `boto3.client("s3", ...)` configurado com as credenciais do `Config`:

- `upload_file(local_path: Path, key: str) -> None` — `client.upload_file(str(local_path), bucket, key)`.
- `object_exists(key: str) -> bool` — `head_object`; `True` se sucesso, `False` se `ClientError` com código `404`/`NoSuchKey` (outros erros propagam).
- `generate_presigned_url(key: str, filename: str, expires_in: int, download: bool = False) -> str` — `client.generate_presigned_url("get_object", Params={..., "ResponseContentDisposition": f'attachment; filename="{filename}"'} if download else {...}, ExpiresIn=expires_in)`.

O client S3 é construído sob demanda (função `_client()`), lendo bucket/região/credenciais de `current_app.config`, seguindo o padrão já usado por `storage.py`/`printing.py` (sem estado global de app fora do factory).

## Mudanças em `app/storage.py`

- `FOLDERS = ("captures", "photos", "discards")` — remove `"back-covers"`.
- Nova função `build_unique_filename(ext: str) -> str`: `f"{timestamp}_{uuid4().hex[:8]}{ext}"`. Sem checagem de colisão em disco (não existe mais pasta local para checar); a combinação timestamp + sufixo aleatório é suficiente.
- Nova função `save_uploaded_image_to_tempfile(file_storage) -> Path`: reaproveita a validação existente (`is_allowed_extension`), grava o conteúdo num `tempfile.NamedTemporaryFile(delete=False, suffix=ext)` e retorna o `Path`. Quem chama é responsável por apagar o arquivo depois (`finally`).
- `save_uploaded_image` (a função atual, que salva direto numa pasta local) continua existindo sem mudanças — ainda não é usada por `back-covers`, mas nada mais depende dela ser removida.

## Mudanças em `app/routes.py`

### `POST /print`

```python
root = current_app.config["STORAGE_ROOT"]
file_storage = request.files.get("image")

try:
    temp_path = storage.save_uploaded_image_to_tempfile(file_storage)
except ValueError as exc:
    return jsonify({"success": False, "message": str(exc)}), 400

try:
    printing.print_image(temp_path)
    filename = storage.build_unique_filename(temp_path.suffix)
    s3_storage.upload_file(temp_path, f"back-covers/{filename}")
finally:
    temp_path.unlink(missing_ok=True)

base_url = current_app.config["BASE_URL"].rstrip("/")
return jsonify({
    "success": True,
    "message": "Imagem salva em back-covers; impressão ainda não implementada (stub)",
    "page_url": f"{base_url}/view/{filename}",
})
```

### `GET /view/<filename>`

```python
key = f"back-covers/{filename}"
if not s3_storage.object_exists(key):
    abort(404)

expires_in = current_app.config["S3_PRESIGNED_URL_EXPIRES"]
image_url = s3_storage.generate_presigned_url(key, filename, expires_in)
download_url = s3_storage.generate_presigned_url(key, filename, expires_in, download=True)
return render_template("view.html", filename=filename, image_url=image_url, download_url=download_url)
```

### `GET /files/<folder>/<filename>`

Sem mudança de código. Como `"back-covers"` sai de `storage.FOLDERS`, o `if folder not in storage.FOLDERS: abort(404)` já cobre o caso.

## Mudança em `app/templates/view.html`

```html
<a id="download-btn" class="btn btn-secondary" href="{{ download_url }}">Download</a>
```

Remove o atributo `download="{{ filename }}"` (não confiável cross-origin; quem força o download agora é o `Content-Disposition` da presigned URL).

## Config (`app/config.py` + `.env.example`)

```python
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
S3_PRESIGNED_URL_EXPIRES = int(os.environ.get("S3_PRESIGNED_URL_EXPIRES", "86400"))
```

`.env.example` ganha essas 5 linhas com valores de exemplo (bucket/keys em branco ou placeholder).

## Testes

- Adicionar `moto` (`moto[s3]`) em `requirements-dev.txt`.
- `tests/conftest.py`: nova fixture que ativa `moto`'s `mock_aws()` e cria o bucket de teste antes de cada teste que precisar (usando `AWS_S3_BUCKET` de teste fixo, ex.: `"test-bucket"`, e credenciais fake), garantindo que nenhum teste chama S3 de verdade.
- `tests/test_routes.py`: os testes de `POST /print` e `/view/<filename>` passam a asserir contra o mock S3 (ex.: usar o client `boto3` do `moto` pra confirmar que o objeto foi criado em `back-covers/<filename>`, e testar 404 de `/view` para uma key que não existe no bucket mock).
- Teste novo: `GET /files/back-covers/<filename>` retorna 404 mesmo que o arquivo "exista" no S3 mock (prova que a rota local não serve mais back-covers).

## Erros e casos de borda

- `head_object`/`generate_presigned_url` falhando por credenciais inválidas ou bucket inexistente: deixado propagar como 500 por enquanto (mesmo padrão do projeto para erros de infraestrutura ainda não tratados — ex.: `OSError` de disco cheio em `save_uploaded_image`).
- Upload falhar após a impressão já ter sido "feita" (stub): como impressão é só um stub hoje, não há rollback a considerar nesta fase; passa a ser relevante quando a impressão real for implementada.
