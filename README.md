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
- Windows, com o [SumatraPDF](https://www.sumatrapdfreader.org/) instalado (usado para imprimir a imagem final em `POST /print`)

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
EVENT_LOCATION=                  # opcional; prefixo de local para rodar múltiplas instâncias no mesmo bucket
SUMATRA_PATH=SumatraPDF.exe      # caminho do executável do SumatraPDF (usado para imprimir em /print)
PRINTER_NAME=                    # nome exato da impressora; vazio usa a impressora padrão do Windows
PRINT_SETTINGS=noscale,paper=A4,center   # flags passadas a -print-settings do SumatraPDF (ver nota abaixo sobre por que é noscale)
PRINT_TIMEOUT=60                 # tempo limite (segundos) para o comando de impressão
PRINT_DPI=300                    # resolução (DPI) usada para compor a imagem no canvas A4 antes de imprimir
PRINT_MARGIN_MM=6                # margem de segurança (mm) ao redor da imagem, para não cortar por causa da margem não-imprimível da impressora
```

`EVENT_LOCATION` é opcional e serve para rodar o mesmo bucket S3 compartilhado entre múltiplas instâncias do app em locais diferentes (ex: um evento em SP e outro no RJ simultaneamente) sem colidir. Quando definida (ex: `EVENT_LOCATION=sp`), as imagens finais vão para `back-covers/sp/<arquivo>` em vez de `back-covers/<arquivo>`; cada instância roda com seu próprio `.env` apontando o mesmo `AWS_S3_BUCKET` mas um `EVENT_LOCATION` diferente. Se deixada vazia (padrão), o comportamento é o mesmo de antes — sem prefixo de local.

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

### `GET /relatorio`

Painel operacional com totais e contagem diária separados: **Geradas para impressão**
(`imprimir_imagem_sucesso`), **Apenas QR Code** (`apenas_qrcode_gerado`),
**Capas geradas** (soma das duas anteriores) e **Reimpressões**
(`reimprimir_imagem_sucesso`, sem nova capa no S3). Visualizações, compartilhamentos e
downloads continuam em indicadores próprios. O detalhamento diário também mostra quantas fotos
geradas no editor para impressão e quantas geradas somente para QR Code tiveram a própria
página `/view/<filename>` acessada entre 0 e 60 segundos após a geração. O vínculo é feito
por `data.file` no evento de geração e `data.filename` na visualização, considerando apenas
o mesmo projeto e local. Cada foto conta uma vez, no dia da geração em Brasília (GMT-3), inclusive se o
acesso ocorrer após a meia-noite. Reimpressões não entram nessas duas colunas nem no total de
capas geradas. Isto é um indicador de abertura do link da foto, **não** uma prova
de quem leu o QR Code: os eventos de geração não identificam a pessoa.

Os gráficos mostram capas geradas para impressão e apenas QR Code empilhadas: **Movimento por
horário** agrupa o intervalo de 10:00 a 23:59 em Brasília, destaca a hora de maior movimento
e informa quantas capas foram geradas fora desse intervalo; **Capas por dia** compara os dias
selecionados, inclusive dias sem eventos. Reimpressões, visualizações e outras interações não
entram nos gráficos de capas. Cartões e tabela diária incluem todas as horas.

Lê a coleção `logs` do LogCenter, filtrando por
`LOGCENTER_PROJECT_ID` e pelo local escolhido (SP ou RJ); usa os campos `message` e `timestamp`
(ISO UTC ou BSON datetime). Não confirma papel impresso nem compartilhamento concluído.
Filtre com `inicio` e `fim` no formato `AAAA-MM-DD` (datas de Brasília inclusivas, até 31 dias;
padrão: últimos sete dias). O filtro `event_location=sp` ou `event_location=rj` começa no
`EVENT_LOCATION` configurado quando for SP/RJ, ou em SP caso contrário; outros valores retornam `400`.

Configure no `.env` da aplicação:

```
LOGCENTER_MONGOURL=mongodb://usuario:senha@host:27017
LOGCENTER_MONGO_DB=logcenter_prod
LOGCENTER_MONGO_COLLECTION=logs
# LOGCENTER_PROJECT_ID e EVENT_LOCATION já configurados para o envio de logs
```

`LOGCENTER_MONGO_DB` pode ficar vazio se a URL incluir o nome do banco. Os padrões acima
correspondem à estrutura do LogCenter consultada. Use um usuário MongoDB com permissão
**somente de leitura**. A página **não exige autenticação**, conforme o fluxo desta aplicação:
restrinja o acesso à rota na rede ou no proxy antes de expor o servidor publicamente.
O card "Arquivos removidos" compara fotos geradas no período com as chaves atuais no S3;
o servidor também precisa de `AWS_S3_BUCKET` e permissão de listar o prefixo selecionado.
Se algum log de geração não informar o arquivo, o card mostra `—`, não um zero parcial.
Sem Mongo ou projeto configurado, ou se a consulta falhar, retorna `503` em vez de apresentar
zeros como se fossem dados reais. A resposta usa `Cache-Control: no-store` e não expõe
IPs nem nomes dos arquivos.

#### Versão estática para CloudFront

O endpoint Flask acima consulta o MongoDB quando acessado. Para servir o relatório sem Flask
e sem consultas ao MongoDB por visitante, gere um snapshot local com:

```bash
venv/Scripts/python scripts/export_report.py
```

O comando usa `LOGCENTER_MONGOURL` e `LOGCENTER_PROJECT_ID` do `.env` **somente durante a
exportação**. Ele cria `dist/report/index.html`, `logs.jsonl` e os assets necessários (CSS,
JavaScript, fonte e logo). Publique **apenas o conteúdo de `dist/report/`** em um bucket de
origem do CloudFront, mantendo todos os arquivos no mesmo prefixo, e configure `index.html`
como objeto raiz padrão. Não publique `.env`, o código do servidor ou outros diretórios.
O navegador baixa `logs.jsonl` da mesma origem e aplica os filtros e gráficos localmente;
não há conexão ao MongoDB nem API Flask no carregamento da página estática.

O JSONL contém um evento por linha com apenas horário UTC, tipo de evento, local (SP/RJ) e
um identificador aleatório derivado da foto para correlacionar geração e visualização, além
de um indicador de presença no S3 para as fotos geradas. O card "Arquivos removidos" conta
fotos distintas com evento de geração no período selecionado que não tinham objeto no S3
no momento da exportação; não é uma prova de quando ou por que o arquivo sumiu. A exportação
exige `AWS_S3_BUCKET` e permissão de listar `back-covers/sp/` e `back-covers/rj/`. IP,
user-agent, nomes de arquivos, chaves S3, credenciais e IDs do projeto não são exportados.
O identificador da foto é pseudônimo com chave aleatória nova a cada exportação; cada snapshot
é independente. Mesmo minimizados, horários/eventos podem ser sensíveis: restrinja o acesso
ao CloudFront conforme necessário. `dist/report/` é ignorado pelo Git.

Para atualizar os dados, execute novamente o comando e publique os arquivos atualizados,
incluindo `index.html` e `js/report.js` ao instalar esta versão do relatório. Invalide
`/logs.jsonl`, `/index.html`, `/js/report.js` e `/` no CloudFront ou configure cache curto
para esses objetos;
do contrário o dashboard poderá mostrar um snapshot antigo. A data do filtro usa GMT-3,
com limite de 31 dias e o gráfico horário de 10:00 a 23:59. A página estática deve ser
servida via HTTP(S), não aberta como `file://` (o `fetch` do JSONL é bloqueado nesse modo).

As rotas de API retornam JSON; `/relatorio`, `/photos` e `/view/<filename>` retornam HTML,
`/files/<folder>/<filename>` retorna a imagem e o download redireciona para o S3.

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
| `200` | `{"success": true, "message": "...", "page_url": "http://localhost:5000/view/20260922_143201.jpg"}` | Arquivo salvo com sucesso. `page_url` aponta para a página de visualização/compartilhamento (ver `GET /view/<filename>`). `message` indica se a impressão foi enviada com sucesso ou se falhou (o upload para o S3 acontece de qualquer forma). |
| `400` | `{"success": false, "message": "..."}` | Nenhum arquivo enviado, ou extensão não permitida. |

> A impressão é feita via [SumatraPDF](https://www.sumatrapdfreader.org/) em modo retrato (`app/printing.py`), configurável pelas variáveis `SUMATRA_PATH`, `PRINTER_NAME`, `PRINT_SETTINGS`, `PRINT_TIMEOUT`, `PRINT_DPI` e `PRINT_MARGIN_MM` (ver seção de variáveis de ambiente). Se a impressão falhar (impressora offline, SumatraPDF não encontrado, etc.), o erro é logado e a resposta ainda é `200`/`success: true` — a imagem final continua salva no S3 e acessível via `page_url`, apenas com `message` indicando a falha na impressão.
>
> Antes de mandar para o SumatraPDF, a imagem é recomposta num canvas A4 (`PRINT_DPI`, padrão 300 DPI) com uma margem de segurança em branco ao redor (`PRINT_MARGIN_MM`, padrão 6mm) e impressa a 100% (`noscale`). Isso é proposital: o modo `fit`/`shrink` do próprio SumatraPDF escala a imagem para a "área imprimível" que o driver da impressora reporta, o que na prática variou entre drivers e cortou imagens com conteúdo até a borda (full-bleed) contra a margem física não-imprimível do papel. Compor a imagem nós mesmos, num tamanho A4 exato e com margem conhecida, elimina essa adivinhação.

Exemplo com `curl`:

```bash
curl -X POST http://localhost:5000/print -F "image=@collage.jpg"
```

### `GET /photos`

Galeria HTML com todas as fotos (`.jpg`, `.jpeg`, `.png`) do bucket `AWS_S3_BUCKET`, no prefixo `back-covers/<EVENT_LOCATION>/`. Se `EVENT_LOCATION` estiver vazio, lista `back-covers/` e suas subpastas. A listagem percorre todas as páginas do S3, mostra as fotos mais recentes primeiro e usa URLs presignadas para exibir as imagens.

Cada foto tem um botão **Imprimir** abaixo dela. Durante o envio, o botão fica desabilitado para evitar cliques duplicados; o resultado aparece no próprio cartão, sem sair da galeria.

No editor, o botão de impressão mostra a espera total prevista, por exemplo **Imprimir - 45 min**, incluindo o tempo da própria foto e a fila local. O valor é arredondado para cima em minutos, atualizado ao abrir/retomar a página e a cada 30 segundos enquanto ela estiver visível. Com a fila vazia, a média de 3min30s aparece como **Imprimir - 4 min**. Se o histórico estiver indisponível, o botão continua como **Imprimir**, sem bloquear o envio nem inventar uma previsão. **Apenas Digital** mantém o estilo secundário. Apenas envios aceitos pela impressora entram no histórico; salvar somente a versão digital, desabilitar a impressão ou receber um erro não marca a foto como impressa.

O histórico é local e persistente no **IndexedDB**, compartilhado entre `/editor` e `/photos` na mesma origem/navegador, e separado por bucket, local do evento e impressora. As operações são assíncronas; são guardados somente nomes/chaves e metadados, nunca as imagens. Uma transação atualiza o histórico e a previsão da fila em conjunto, inclusive entre abas. Reimpressões contam como novos envios, sem duplicar a entrada da foto. `/photos` restaura o contorno verde ao carregar e ao recuperar o foco. O verde significa **envio aceito**, não confirmação de saída do papel.

O botão **Estimar horário** usa uma média de **3min30s por envio**: o horário previsto é o maior entre a entrada na fila e o término estimado anterior, mais 3min30s. Para uma foto já enviada, mostra a previsão do último envio; para uma não enviada, simula o próximo lugar na fila, sem imprimir. A data no nome do arquivo aparece apenas como referência (horário do servidor): uma reimpressão entra na fila agora, mesmo que o arquivo seja antigo. A previsão vencida pede confirmação na impressora e não declara conclusão física.

O histórico não consulta o spooler e não inclui impressões anteriores à funcionalidade, nem envios de outros navegadores/dispositivos/origens. Limpar os dados do site (ou usar uma janela privada) pode remover o histórico. Se o armazenamento estiver bloqueado/cheio, a interface avisa, mas não repete uma impressão já aceita. A capacidade do IndexedDB depende do navegador e do espaço disponível. Se o `localStorage` do link do QR Code estiver cheio/bloqueado, o editor passa esse link no fragmento da URL e continua para o QR Code sem reenviar a impressão.

Para executar os testes JavaScript do histórico e da interface: `npm ci` e `npm test` (Node.js 20+). `fake-indexeddb` é uma dependência apenas de testes; o navegador usa seu IndexedDB nativo, sem bibliotecas adicionais.

As credenciais configuradas precisam de `s3:ListBucket` no bucket (para o prefixo configurado) e `s3:GetObject` nas fotos. Uma pasta vazia mostra uma mensagem; falhas de acesso ao S3 retornam uma página de erro com status `502`.

### `POST /photos/print`

Recebe JSON com `key`, a chave completa do objeto no S3, por exemplo `{"key": "back-covers/sp/foto.png"}`. Baixa a imagem original para uma pasta temporária, envia para a impressora configurada (`SUMATRA_PATH` / `PRINTER_NAME`) e remove os arquivos temporários, inclusive em caso de erro. Não faz outro upload nem cria uma cópia no bucket.

Aceita apenas imagens dentro do prefixo configurado. Retorna `200` com `success: true` e `printed: true` quando o comando de impressão é aceito; `400` para uma chave inválida; `404` se a foto não existir; `409` se a impressão estiver desabilitada; ou `502` se houver falha no download ou na impressão. Registra os eventos `reimprimir_imagem_sucesso` e `reimprimir_imagem_falhou`.

> Estes endpoints são operacionais e não têm autenticação própria, assim como o fluxo de impressão existente. Restrinja o acesso à rede da operação ou proteja as rotas no proxy antes de expô-las publicamente: a galeria permite visualizar todas as fotos do prefixo e acionar a impressora do servidor.

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
