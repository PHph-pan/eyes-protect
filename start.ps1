$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$DesktopReminder = Join-Path $Root "desktop_reminder.py"

function Assert-Command {
    param(
        [string]$Name,
        [string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "未找到 $Name。$InstallHint" -ForegroundColor Red
        exit 1
    }
}

Assert-Command "npm" "请先安装 Node.js/npm，并确保 npm 已加入 PATH。"

if (-not (Test-Path (Join-Path $Backend "requirements.txt"))) {
    Write-Host "未找到 backend\requirements.txt，请确认在项目根目录运行 start.ps1。" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $Frontend "package.json"))) {
    Write-Host "未找到 frontend\package.json，请确认在项目根目录运行 start.ps1。" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $DesktopReminder)) {
    Write-Host "未找到 desktop_reminder.py，请确认在项目根目录运行 start.ps1。" -ForegroundColor Red
    exit 1
}

$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $Python = "python"
} else {
    Write-Host "未找到 Python。请先安装 Python，或在 backend 目录创建 .venv。" -ForegroundColor Red
    exit 1
}

& $Python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "后端依赖未安装。请先运行：cd backend; pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "前端依赖未安装。请先运行：cd frontend; npm install" -ForegroundColor Red
    exit 1
}

$BackendCommand = "Set-Location `"$Backend`"; & `"$Python`" -m uvicorn app.main:app --reload"
$FrontendCommand = "Set-Location `"$Frontend`"; npm run dev"
$ReminderCommand = "Set-Location `"$Root`"; & `"$Python`" desktop_reminder.py"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCommand
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", $FrontendCommand
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", $ReminderCommand

Write-Host "已启动后端、前端和桌面护眼提醒伴侣。" -ForegroundColor Green
Write-Host "前端通常运行在 http://127.0.0.1:5173"
