$ErrorActionPreference = "Stop"

Write-Host "J.A.R.V.I.S Windows Kurulum" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python bulunamadi. Python 3.10+ kurup tekrar deneyin." -ForegroundColor Red
    exit 1
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host ""
Write-Host "Kurulum tamamlandi. Baslatmak icin:" -ForegroundColor Green
Write-Host "python main.py"
