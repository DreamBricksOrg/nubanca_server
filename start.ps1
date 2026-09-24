<#
.SYNOPSIS
  Sobe o ngrok e a aplicacao Flask juntos, usando a URL publica do ngrok como BASE_URL.

.PARAMETER Port
  Porta local da aplicacao. Se omitida, usa PORT do .env (padrao 5000).
#>
param(
    [int]$Port
)

Set-Location $PSScriptRoot

# Resolve a porta: parametro > .env > padrao 5000
if (-not $Port) {
    $Port = 5000
    $envFile = Join-Path $PSScriptRoot ".env"
    if (Test-Path $envFile) {
        $portLine = Get-Content $envFile | Where-Object { $_ -match "^\s*PORT\s*=" } | Select-Object -Last 1
        if ($portLine) {
            $value = ($portLine -split "=", 2)[1].Trim()
            if ($value) { $Port = [int]$value }
        }
    }
}

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Error "ngrok nao encontrado no PATH. Instale o ngrok (https://ngrok.com/download) e rode 'ngrok config add-authtoken <token>' antes de usar este script."
    exit 1
}

$pythonExe = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Error "venv nao encontrado em '$pythonExe'. Crie o ambiente virtual e instale as dependencias antes de rodar este script."
    exit 1
}

Write-Host "Iniciando ngrok na porta $Port..."
$ngrokLog = Join-Path $PSScriptRoot "ngrok.log"
$ngrokProcess = Start-Process -FilePath "ngrok" -ArgumentList @("http", "$Port", "--log=stdout") `
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
