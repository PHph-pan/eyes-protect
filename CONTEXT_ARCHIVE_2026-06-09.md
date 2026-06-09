# Eyes Protect Context Archive - 2026-06-09

This archive summarizes the previous Codex thread so future work can resume without rereading the whole conversation.

## Source Thread

- Thread title: 完善护眼提醒工具计划
- Thread id: 019ea4de-4880-7361-8130-37ea721f1f76
- Project path: D:\Files\code\pythonProjects\eyes-protect
- Original product goal: build an eye-protection reminder tool with configurable reminder intervals and very obvious reminders, using FastAPI + SQLite + Vue.

## Product Direction

The project evolved from a web-style MVP into a local Windows desktop app:

- FastAPI runs locally on the user's machine.
- Vue is used for the control/settings UI.
- SQLite stores settings and timer state.
- A Python desktop companion displays strong local reminders.
- The app should be usable by non-programmers through a Windows installer.
- No remote/cloud server is required for the MVP.

## Implemented Functional Areas

### Core Reminder MVP

- Configurable work reminder interval.
- Configurable rest duration.
- Strong reminder UX through webpage overlay and desktop companion.
- Settings persisted in SQLite.

### Backend-Owned Timer State

The countdown state was moved from Vue into the backend so the state survives page refreshes and browser closure while the backend is running.

Timer states include:

- idle
- running
- alerting
- resting
- paused

Important timer APIs implemented in the previous thread:

- GET /api/timer
- POST /api/timer/start
- POST /api/timer/pause
- POST /api/timer/resume
- POST /api/timer/reset
- POST /api/timer/start-rest
- POST /api/timer/snooze
- POST /api/timer/skip

Behavior:

- GET /api/timer advances timer state before returning.
- When work time expires, backend enters alerting and creates a desktop alert.
- Desktop companion polling can trigger backend state advancement even when the web page is closed.
- Desktop alert acknowledgement moves the timer into resting when the alert id matches.

### Desktop Companion

- desktop_reminder.py polls the backend for pending desktop alerts.
- It displays a prominent desktop reminder.
- It reports acknowledgement back to the backend.
- Previous `closed` semantics were upgraded toward `acknowledged`; compatibility with old `closed` status was considered.

### Desktop Companion Health Status

Added health/heartbeat visibility so the user can tell whether strong desktop reminders are actually active.

Backend:

- POST /api/desktop-companion/heartbeat
- GET /api/desktop-companion/status

Frontend:

- Shows desktop companion status as connected/disconnected.
- Expected behavior: after desktop_reminder.py starts, status becomes connected within a few seconds; after it stops, status becomes disconnected after roughly 5 seconds.

### Do Not Disturb Periods

Added daily repeating do-not-disturb periods.

Backend:

- New do_not_disturb_periods table.
- GET /api/do-not-disturb
- PUT /api/do-not-disturb
- Timer state machine checks current time against enabled periods.

Behavior:

- Supports normal periods like 12:00-13:30.
- Supports cross-midnight periods like 22:00-07:00.
- If work reminder expires during a do-not-disturb period, no web/desktop strong reminder is created.
- The reminder is postponed until the period ends.
- Timer response includes whether it is currently in do-not-disturb mode, the matched period name, and the period end time.

Frontend:

- Settings panel can add/delete/enable/disable do-not-disturb periods.
- Page displays a subtle "do not disturb" status when active.

## Startup And Local Development

A Windows start script was planned/implemented earlier:

- start.ps1 starts backend, frontend, and desktop companion in separate PowerShell windows.
- README was updated to recommend using .\start.ps1 while keeping manual startup instructions.

Manual validation commands used in prior instructions:

```powershell
cd backend
pytest
```

```powershell
cd frontend
npm install
npm run build
```

```powershell
python packaged_app.py
```

## Windows Installer Direction

The previous thread decided the best non-programmer distribution path is:

- Build Vue static assets.
- Serve Vue through FastAPI in the packaged app.
- Store user SQLite data under %APPDATA%\EyesProtect\eyes_protect.db.
- Use PyInstaller to create dist\EyesProtect\EyesProtect.exe.
- Use Inno Setup 6 to create dist\installer\EyesProtect-Setup-0.1.0.exe.

Files created or modified for packaging:

- packaged_app.py
- packaging\EyesProtect.spec
- packaging\EyesProtect.iss
- packaging\build_windows.ps1
- build_windows_installer.ps1
- packaging\README.md
- WINDOWS_INSTALLER.md
- VERSION
- .gitignore

Packaging notes:

- dist\EyesProtect\EyesProtect.exe is the runnable app folder, not the final installer.
- dist\installer\EyesProtect-Setup-0.1.0.exe is the expected final installer.
- Inno Setup can be installed with:

```powershell
winget install --id JRSoftware.InnoSetup -e -s winget -i
```

After installing Inno Setup, run from project root:

```powershell
.\build_windows_installer.ps1
```

## Recent Packaging Fixes

The latest part of the previous thread focused on build issues found by the user.

### PyInstaller wrong script path

Observed error:

```text
ERROR: script 'D:\Files\code\pythonProjects\packaged_app.py' not found
```

Cause:

- packaging\EyesProtect.spec calculated the project root incorrectly.
- It looked one directory too high.

Fix applied:

- packaging\EyesProtect.spec was updated to resolve packaged_app.py under D:\Files\code\pythonProjects\eyes-protect.

### Build script continued after failure

Problem:

- build_windows.ps1 continued after PyInstaller failed and printed a misleading message that the app folder was ready.

Fix applied:

- packaging\build_windows.ps1 now stops when PyInstaller or Inno Setup fails.
- Inno Setup lookup was expanded to PATH, Program Files, Program Files (x86), and user install paths.

### Inno Setup illegal null character

Observed error:

```text
Illegal null character on line 1.
```

Cause:

- packaging\EyesProtect.iss contained invalid null/encoding characters.

Fix applied:

- packaging\EyesProtect.iss was rewritten cleanly.
- packaging\build_windows.ps1 now generates a clean UTF-8 copy before invoking Inno Setup.

### Too many changed files in VS Code

Observed:

- User saw about 1000 changed files after building.

Explanation:

- These were build artifacts from PyInstaller, frontend build, and packaging virtual environment.
- They are not source changes.

Fix applied:

- .gitignore was added/updated to ignore likely generated paths such as build\, dist\, .packaging-venv\, and frontend\dist\.

## Current Expected User Flow

To build final installer:

```powershell
cd D:\Files\code\pythonProjects\eyes-protect
.\build_windows_installer.ps1
```

Expected outputs:

```text
D:\Files\code\pythonProjects\eyes-protect\dist\EyesProtect\EyesProtect.exe
D:\Files\code\pythonProjects\eyes-protect\dist\installer\EyesProtect-Setup-0.1.0.exe
```

If only dist\EyesProtect\EyesProtect.exe exists:

- PyInstaller app folder succeeded.
- Inno Setup installer step did not run or failed.

If neither exists:

- Build did not complete.

Quick checks for the user:

```powershell
Test-Path .\dist\installer\EyesProtect-Setup-0.1.0.exe
Test-Path .\dist\EyesProtect\EyesProtect.exe
```

## Important Caveats

- The previous Codex window repeatedly could not run local shell commands because the command channel failed with CreateProcessWithLogonW failed: 2.
- Some validation was therefore based on user-provided logs and static edits rather than direct local test execution.
- The user did run build_windows_installer.ps1 and shared logs/screenshots, which drove the packaging fixes.
- Tests/builds should be rerun locally after any further changes.

## Recommended Next Steps

1. Run the latest build script again from the project root.
2. Confirm whether dist\installer\EyesProtect-Setup-0.1.0.exe is generated.
3. If it still fails, inspect the new error after the UTF-8 Inno script fix.
4. Run backend tests:

```powershell
cd backend
pytest
```

5. Run frontend build:

```powershell
cd frontend
npm run build
```

6. Check git status and ensure only real source/package files remain changed, not build artifacts.

## Non-Programmer Product Notes

- For ordinary users, the recommended distribution is a Windows installer.
- The local backend is an implementation detail; users should not need to know about FastAPI, Python, Node, npm, or uvicorn.
- Closing the browser does not necessarily exit the background reminder process in the first packaged version.
- A future improvement should add a system tray icon or a clear quit mechanism.
- Future upgrades can be delivered as new installer versions that overwrite program files while keeping user data in %APPDATA%\EyesProtect.
