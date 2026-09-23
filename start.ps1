<#
.SYNOPSIS
  Sobe o ngrok e a aplicacao Flask juntos, usando a URL publica do ngrok como BASE_URL.

.PARAMETER Port
  Porta local da aplicacao. Se omitida, usa PORT do .env (padrao 5000).

.PARAMETER BaseUrl
  Dominio reservado do ngrok (ex: nubancasp.ngrok.app) a ser usado como BASE_URL.
  Se omitido, usa BASE_URL do .env; se nenhum dos dois estiver definido, o ngrok
  sorteia uma URL aleatoria a cada execucao.
#>
param(
    [int]$Port,
    [string]$BaseUrl
)

Set-Location $PSScriptRoot
$envFile = Join-Path $PSScriptRoot ".env"

function Get-EnvValue {
    param([string]$Name)
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$Name\s*=" } | Select-Object -Last 1
        if ($line) {
            $value = ($line -split "=", 2)[1].Trim()
            if ($value) { return $value }
        }
    }
    return $null
}

# Resolve a porta: parametro > .env > padrao 5000
if (-not $Port) {
    $Port = 5000
    $portValue = Get-EnvValue -Name "PORT"
    if ($portValue) { $Port = [int]$portValue }
}

# Resolve o dominio reservado (opcional): parametro > .env > nenhum (URL dinamica)
if (-not $BaseUrl) {
    $BaseUrl = Get-EnvValue -Name "BASE_URL"
}
if ($BaseUrl) { $BaseUrl = $BaseUrl.TrimEnd("/") }

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Error "ngrok nao encontrado no PATH. Instale o ngrok (https://ngrok.com/download) e rode 'ngrok config add-authtoken <token>' antes de usar este script."
    exit 1
}

$pythonExe = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Error "venv nao encontrado em '$pythonExe'. Crie o ambiente virtual e instale as dependencias antes de rodar este script."
    exit 1
}

# Garante que nao existe um ngrok orfao de uma execucao anterior ainda escutando
# na porta 4040 - senao o novo agente sobe numa porta alternativa (4041+) e o
# script acaba consultando a API do processo antigo, pegando a URL errada.
$stale = Get-Process ngrok -ErrorAction SilentlyContinue
if ($stale) {
    Write-Host "Encerrando instancia antiga do ngrok (PID $($stale.Id -join ', '))..."
    $stale | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

$ngrokArgs = @("http")
if ($BaseUrl) {
    Write-Host "Iniciando ngrok na porta $Port com dominio reservado $BaseUrl..."
    $ngrokArgs += "--url=$BaseUrl"
} else {
    Write-Host "Iniciando ngrok na porta $Port (URL dinamica, BASE_URL nao definido)..."
}
$ngrokArgs += "$Port"
$ngrokArgs += "--log=stdout"

$ngrokLog = Join-Path $PSScriptRoot "ngrok.log"
$ngrokProcess = Start-Process -FilePath "ngrok" -ArgumentList $ngrokArgs `
    -PassThru -WindowStyle Hidden -RedirectStandardOutput $ngrokLog

try {
    Write-Host "Aguardando o ngrok publicar a URL..."
    $publicUrl = $null
    $maxAttempts = 30
    $attempt = 0

    while (-not $publicUrl -and $attempt -lt $maxAttempts) {
        Start-Sleep -Seconds 1
        $attempt++
        try {
            $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop
            $tunnel = $tunnels.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
            if (-not $tunnel) {
                $tunnel = $tunnels.tunnels | Select-Object -First 1
            }
            if ($tunnel) {
                $publicUrl = $tunnel.public_url
            }
        } catch {
            # API do ngrok ainda nao subiu; tenta de novo no proximo loop.
        }
    }

    if (-not $publicUrl) {
        throw "Nao foi possivel obter a URL publica do ngrok apos $maxAttempts tentativas. Veja '$ngrokLog' para detalhes."
    }

    if ($BaseUrl -and ($publicUrl.TrimEnd("/") -ne $BaseUrl)) {
        throw "O ngrok retornou uma URL diferente da reservada. Esperado '$BaseUrl', recebido '$publicUrl'. " +
              "Verifique se o dominio esta corretamente reservado na sua conta do ngrok, e confira '$ngrokLog' para detalhes."
    }

    Write-Host "ngrok pronto: $publicUrl"
    Write-Host "Iniciando a aplicacao Flask (BASE_URL=$publicUrl, PORT=$Port)..."

    $env:BASE_URL = $publicUrl
    $env:PORT = "$Port"

    & $pythonExe run.py
}
finally {
    Write-Host "Encerrando ngrok..."
    if ($ngrokProcess -and -not $ngrokProcess.HasExited) {
        Stop-Process -Id $ngrokProcess.Id -Force -ErrorAction SilentlyContinue
    }
    # No Windows o processo do ngrok as vezes sobrevive ao Stop-Process por -Id;
    # garante que nenhuma instancia fique pendurada.
    Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
