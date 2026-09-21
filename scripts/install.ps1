$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $ProjectDir "scripts\ai_platform.py"

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $Installer setup @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $Installer setup @args
} else {
    throw "Python 3.11 or newer is required."
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
