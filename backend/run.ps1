# Veritas Engine - local backend launcher (Windows / PowerShell)
# Usage:  ./run.ps1            (creates .venv on first run, installs deps, starts API on :8000)
#         ./run.ps1 -Port 9000
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
