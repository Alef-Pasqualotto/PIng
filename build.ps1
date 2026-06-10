$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv-build")) {
    py -3 -m venv .venv-build
}

& ".venv-build\Scripts\python.exe" -m pip install --upgrade pip
& ".venv-build\Scripts\python.exe" -m pip install -r requirements-dev.txt
& ".venv-build\Scripts\python.exe" tools\generate_icon.py
& ".venv-build\Scripts\python.exe" -m pytest -q
& ".venv-build\Scripts\pyinstaller.exe" --noconfirm --clean ping.spec

Write-Host "Aplicativo criado em dist\PIng\PIng.exe"
Write-Host "Para criar o instalador, execute: iscc installer.iss"
