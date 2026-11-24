# Inicia o MinePlan Control em http://localhost:8000
# Uso: .\iniciar.ps1            (inicia o servidor)
#      .\iniciar.ps1 -Exemplo   (recria o banco com uma semana de dados de exemplo antes)
param([switch]$Exemplo, [int]$Porta = 8000)

$raiz = $PSScriptRoot
if (-not (Test-Path "$raiz\.venv")) {
    python -m venv "$raiz\.venv"
    & "$raiz\.venv\Scripts\python" -m pip install -r "$raiz\requirements.txt"
}
Set-Location "$raiz\backend"
if ($Exemplo) { & "$raiz\.venv\Scripts\python" -m app.seed --limpar }
Write-Host "MinePlan Control em http://localhost:$Porta  (API: http://localhost:$Porta/docs)"
& "$raiz\.venv\Scripts\python" -m uvicorn app.main:app --host 0.0.0.0 --port $Porta
