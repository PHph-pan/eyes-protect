from __future__ import annotations

import argparse
import os
import runpy
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional


APP_NAME = "EyesProtect"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def add_backend_to_path(root: Path) -> None:
    candidates = [
        root / "backend",
        Path(__file__).resolve().parent / "backend",
    ]
    for candidate in candidates:
        if candidate.exists():
            text = str(candidate)
            if text not in sys.path:
                sys.path.insert(0, text)


def configure_sqlite_path() -> Path:
    db_path = user_data_dir() / "eyes_protect.db"
    os.environ.setdefault("EYES_PROTECT_DATA_DIR", str(user_data_dir()))
    os.environ.setdefault("EYES_PROTECT_DB_PATH", str(db_path))
    os.environ.setdefault("EYES_PROTECT_DATABASE_PATH", str(db_path))
    os.environ.setdefault("EYES_PROTECT_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    return db_path


def patch_database_module(db_path: Path) -> None:
    try:
        from app import database
    except Exception:
        return

    for name in ("DATABASE_PATH", "DB_PATH", "DATABASE_FILE", "DATABASE"):
        if hasattr(database, name):
            current = getattr(database, name)
            setattr(database, name, str(db_path) if isinstance(current, str) else db_path)

    if hasattr(database, "DATABASE_URL"):
        setattr(database, "DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    for name, value in list(vars(database).items()):
        if not any(part in name.upper() for part in ("DB", "DATABASE")):
            continue
        if isinstance(value, Path) and value.suffix.lower() == ".db":
            setattr(database, name, db_path)
        elif isinstance(value, str) and value.lower().endswith(".db"):
            setattr(database, name, str(db_path))


def frontend_dist_dir(root: Path) -> Optional[Path]:
    candidates = [
        root / "frontend" / "dist",
        Path(__file__).resolve().parent / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


def mount_frontend(app, static_dir: Path) -> None:
    from fastapi import Response
    from fastapi.responses import FileResponse
    from fastapi.routing import APIRoute

    index_file = static_dir / "index.html"

    app.router.routes = [
        route
        for route in app.router.routes
        if not (isinstance(route, APIRoute) and getattr(route, "path", None) == "/")
    ]

    @app.get("/", include_in_schema=False)
    async def packaged_frontend_index():
        return FileResponse(index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def packaged_frontend_assets(full_path: str):
        if full_path.startswith("api/"):
            return Response(status_code=404)

        target = (static_dir / full_path).resolve()
        try:
            target.relative_to(static_dir.resolve())
        except ValueError:
            return FileResponse(index_file)

        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(index_file)


def build_fastapi_app():
    root = resource_root()
    add_backend_to_path(root)
    db_path = configure_sqlite_path()
    patch_database_module(db_path)

    from app.main import app

    static_dir = frontend_dist_dir(root)
    if static_dir:
        mount_frontend(app, static_dir)

    return app


class LazyAsgiApp:
    def __init__(self) -> None:
        self._app = None

    async def __call__(self, scope, receive, send) -> None:
        if self._app is None:
            self._app = build_fastapi_app()
        await self._app(scope, receive, send)


app = LazyAsgiApp()


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def existing_server_is_app(host: str, port: int) -> bool:
    api_url = f"http://{host}:{port}/api/settings"
    frontend_url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(api_url, timeout=1.5) as response:
            api_body = response.read(2048).decode("utf-8", errors="ignore")
            api_ok = response.status == 200 and "reminder" in api_body

        with urllib.request.urlopen(frontend_url, timeout=1.5) as response:
            frontend_body = response.read(4096).decode("utf-8", errors="ignore").lower()
            frontend_ok = (
                response.status == 200
                and "<html" in frontend_body
                and ("id=\"app\"" in frontend_body or "/assets/" in frontend_body)
            )

        return api_ok and frontend_ok
    except Exception:
        return False


def show_error(message: str) -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
            return
        except Exception:
            pass
    print(message)


def wait_for_server(host: str, port: int, timeout_seconds: int = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if port_is_open(host, port):
            return True
        time.sleep(0.25)
    return False


def start_desktop_companion(host: str, port: int) -> subprocess.Popen:
    api_base_url = f"http://{host}:{port}/api"
    env = os.environ.copy()
    env["EYES_PROTECT_API_BASE_URL"] = api_base_url
    env["EYES_PROTECT_API_URL"] = api_base_url

    if getattr(sys, "frozen", False):
        args = [sys.executable, "--desktop-companion", "--api-base-url", api_base_url]
    else:
        args = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--desktop-companion",
            "--api-base-url",
            api_base_url,
        ]

    stdout = open(log_dir() / "desktop_companion.log", "a", encoding="utf-8")
    stderr = open(log_dir() / "desktop_companion_error.log", "a", encoding="utf-8")

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    return subprocess.Popen(
        args,
        env=env,
        stdout=stdout,
        stderr=stderr,
        creationflags=creationflags,
    )


def run_desktop_companion(api_base_url: str) -> None:
    os.environ["EYES_PROTECT_API_BASE_URL"] = api_base_url
    os.environ["EYES_PROTECT_API_URL"] = api_base_url

    root = resource_root()
    script = root / "desktop_reminder.py"
    if script.exists():
        sys.argv = [str(script)]
        runpy.run_path(str(script), run_name="__main__")
        return

    import desktop_reminder

    for name in ("API_BASE_URL", "BASE_URL"):
        if hasattr(desktop_reminder, name):
            setattr(desktop_reminder, name, api_base_url)

    main = getattr(desktop_reminder, "main", None)
    if callable(main):
        main()
        return

    raise RuntimeError("desktop_reminder.py does not expose a runnable entry point.")


def run_server(host: str, port: int) -> None:
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def run_application(host: str, port: int, no_browser: bool, no_companion: bool) -> int:
    url = f"http://{host}:{port}"
    if port_is_open(host, port):
        if existing_server_is_app(host, port):
            if not no_browser:
                webbrowser.open(url)
            return 0

        show_error(
            f"{APP_NAME} cannot start because {host}:{port} is already in use.\n\n"
            "If you are running the development backend, stop uvicorn first, then run "
            "python packaged_app.py again."
        )
        return 1

    server_thread = threading.Thread(target=run_server, args=(host, port), daemon=True)
    server_thread.start()

    if not wait_for_server(host, port):
        show_error(f"{APP_NAME} server did not start within the expected time.")
        return 1

    companion_process: Optional[subprocess.Popen] = None
    if not no_companion:
        companion_process = start_desktop_companion(host, port)

    if not no_browser:
        webbrowser.open(url)

    try:
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if companion_process and companion_process.poll() is None:
            companion_process.terminate()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local EyesProtect desktop app.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-desktop-companion", action="store_true")
    parser.add_argument("--desktop-companion", action="store_true")
    parser.add_argument(
        "--api-base-url",
        default=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/api",
        help="API base URL used by the desktop companion process.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.desktop_companion:
        run_desktop_companion(args.api_base_url)
        return 0

    return run_application(
        host=args.host,
        port=args.port,
        no_browser=args.no_browser,
        no_companion=args.no_desktop_companion,
    )


if __name__ == "__main__":
    raise SystemExit(main())
