$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildScript = Join-Path $ProjectRoot "packaging\build_windows.ps1"

if (-not (Test-Path -LiteralPath $BuildScript)) {
    throw "Build script was not found: $BuildScript"
}

& $BuildScript @args
exit $LASTEXITCODE
