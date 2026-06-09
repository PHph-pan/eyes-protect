$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PackagingRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $PackagingRoot

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-Tool {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required tool was not found on PATH: $Name"
    }

    return $command.Source
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$WorkingDirectory = $ProjectRoot
    )

    $previousLocation = Get-Location
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($exitCode -ne 0) {
        throw "$FilePath failed with exit code $exitCode"
    }
}

function Find-InnoSetupCompiler {
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $roots = @()
    if ($env:ProgramFiles) {
        $roots += $env:ProgramFiles
    }

    $ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($ProgramFilesX86) {
        $roots += $ProgramFilesX86
    }

    if ($env:LOCALAPPDATA) {
        $roots += (Join-Path $env:LOCALAPPDATA "Programs")
    }

    $roots = $roots | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($root in $roots) {
        $candidate = Join-Path $root "Inno Setup 6\ISCC.exe"
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    return $null
}

Write-Step "Check required tools"
$Npm = Resolve-Tool "npm"
$Python = Resolve-Tool "python"

$FrontendRoot = Join-Path $ProjectRoot "frontend"
$FrontendDist = Join-Path $FrontendRoot "dist\index.html"
$BackendRequirements = Join-Path $ProjectRoot "backend\requirements.txt"
$SpecFile = Join-Path $ProjectRoot "packaging\EyesProtect.spec"
$InstallerScript = Join-Path $ProjectRoot "packaging\EyesProtect.iss"
$VenvRoot = Join-Path $ProjectRoot ".packaging-venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$PyInstaller = Join-Path $VenvRoot "Scripts\pyinstaller.exe"
$AppExe = Join-Path $ProjectRoot "dist\EyesProtect\EyesProtect.exe"
$InstallerExe = Join-Path $ProjectRoot "dist\installer\EyesProtect-Setup-0.1.0.exe"

if (-not (Test-Path -LiteralPath $FrontendRoot)) {
    throw "Frontend directory was not found: $FrontendRoot"
}
if (-not (Test-Path -LiteralPath $BackendRequirements)) {
    throw "Backend requirements file was not found: $BackendRequirements"
}
if (-not (Test-Path -LiteralPath $SpecFile)) {
    throw "PyInstaller spec file was not found: $SpecFile"
}
if (-not (Test-Path -LiteralPath $InstallerScript)) {
    throw "Inno Setup script was not found: $InstallerScript"
}

Write-Step "Build Vue frontend"
Invoke-Native -FilePath $Npm -Arguments @("install") -WorkingDirectory $FrontendRoot
Invoke-Native -FilePath $Npm -Arguments @("run", "build") -WorkingDirectory $FrontendRoot

if (-not (Test-Path -LiteralPath $FrontendDist)) {
    throw "Vue build did not create expected file: $FrontendDist"
}

Write-Step "Create packaging virtual environment"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Invoke-Native -FilePath $Python -Arguments @("-m", "venv", $VenvRoot)
}

Write-Step "Install Python dependencies"
Invoke-Native -FilePath $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Native -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-r", $BackendRequirements)
Invoke-Native -FilePath $VenvPython -Arguments @("-m", "pip", "install", "pyinstaller")

if (-not (Test-Path -LiteralPath $PyInstaller)) {
    throw "PyInstaller executable was not found after installation: $PyInstaller"
}

Write-Step "Build Windows app folder with PyInstaller"
Invoke-Native -FilePath $PyInstaller -Arguments @("--noconfirm", "--clean", $SpecFile)

if (-not (Test-Path -LiteralPath $AppExe)) {
    throw "PyInstaller finished but expected app executable was not created: $AppExe"
}

Write-Step "Build installer if Inno Setup is available"
$Iscc = Find-InnoSetupCompiler
if (-not $Iscc) {
    Write-Warning "Inno Setup was not found. PyInstaller app folder is ready under dist\EyesProtect."
    Write-Warning "Install Inno Setup 6 and run this script again to generate a setup installer."
    Write-Host "Done: $AppExe" -ForegroundColor Green
    exit 0
}

$SanitizedInstallerScript = Join-Path $ProjectRoot "build\EyesProtect.iss"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SanitizedInstallerScript) | Out-Null

$InstallerText = [System.IO.File]::ReadAllText($InstallerScript, [System.Text.Encoding]::UTF8)
$InstallerText = $InstallerText -replace "`0", ""
[System.IO.File]::WriteAllText(
    $SanitizedInstallerScript,
    $InstallerText,
    [System.Text.UTF8Encoding]::new($false)
)

Invoke-Native -FilePath $Iscc -Arguments @($SanitizedInstallerScript)

if (-not (Test-Path -LiteralPath $InstallerExe)) {
    throw "Inno Setup finished but expected installer was not created: $InstallerExe"
}

Write-Host "Done: $InstallerExe" -ForegroundColor Green
