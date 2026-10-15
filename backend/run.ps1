# Veritas Engine - local backend launcher (Windows / PowerShell)
# Usage:  ./run.ps1              (creates .venv on first run, installs deps, starts the app on :8000)
#         ./run.ps1 -Port 9000
#         ./run.ps1 -Full        (also installs full media forensics: bundled FFmpeg + C2PA)
#         ./run.ps1 -Whisper     (also installs offline transcription; implies -Full)
param([int]$Port = 8000, [switch]$Full, [switch]$Whisper)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv")) { python -m venv .venv }
$requirements = "requirements.txt"
if ($Full) { $requirements = "requirements-media.txt" }
if ($Whisper) { $requirements = "requirements-whisper.txt" }
& .\.venv\Scripts\python.exe -m pip install -q -r $requirements
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
