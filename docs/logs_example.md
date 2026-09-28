# Logs

Todos os logs são enviados via `log_event(level, message, *, data=None, status=None)` em
[`app/logcenter.py`](../app/logcenter.py). Tags sempre `["server", EVENT_LOCATION]`
(`EVENT_LOCATION` vem de `Config.EVENT_LOCATION`). `data.event_location` é adicionado
automaticamente em **todo** log, além dos campos específicos de cada evento listados na
coluna "Data" abaixo. `status` é a mensagem do código HTTP em snake_case (ex.: 200 →
`success`, 204 → `no_content`, 302 → `found`, 404 → `not_found`). Exemplo completo do
envio em [`logs_example.txt`](logs_example.txt).

| Rota | Message (snake_case, PT-BR) | Level | Quando dispara | Data (além de `event_location`) |
|---|---|---|---|---|
| `GET /image` | `tratamento_imagem_falhou` | ERROR | Falha do ImageMagick ao tratar a imagem promovida | `file`, `error` |
| `POST /discard` | `descartar_imagem_chamada` | DEBUG | Sempre, ao final da rota (`not_found` se não há foto para descartar, `success` se descartou) | — |
| `POST /print` | `imprimir_imagem_chamada` | DEBUG | Sempre, ao final da rota (`bad_request` se upload inválido, `success` caso contrário) | — |
| `POST /print` | `imprimir_imagem_falhou` | ERROR | Falha ao imprimir via SumatraPDF | `file`, `error` |
| `POST /print` | `imprimir_imagem_sucesso` | INFO | Impressão concluída com sucesso | `file` |
| `GET /view/<filename>` | `visualizar_foto_acessada` | INFO | Página `/view` acessada com sucesso | `filename`, `user_agent`, `browser`, `platform`, `ip` |
| `POST /view/<filename>/share` | `compartilhar_imagem` | INFO | Compartilhamento da imagem em `/view` | `filename`, `user_agent`, `browser`, `platform`, `ip` |
| `GET /view/<filename>/download` | `baixar_imagem` | INFO | Download da imagem em `/view` | `filename`, `user_agent`, `browser`, `platform`, `ip` |
| `GET /files/<folder>/<filename>` | `servir_arquivo_chamada` | DEBUG | Sempre, ao final da rota (`not_found` se pasta desconhecida, `success` se serviu o arquivo) | `folder`, `filename` |
