# Windows 本地安装包

这套打包方案仍然使用当前架构：FastAPI + Vue + SQLite + Python 桌面伴侣，但用户安装后不需要手动运行 Python、Node、`uvicorn` 或 `npm run dev`。

## 产物形态

- `packaged_app.py`：安装包运行入口，负责启动本地 FastAPI、打开网页界面、拉起桌面伴侣。
- `frontend/dist`：Vue 构建后的静态资源，由 FastAPI 在本机直接提供。
- SQLite 数据库：保存到 `%APPDATA%\EyesProtect\eyes_protect.db`，覆盖安装新版时不会丢配置。
- `packaging/EyesProtect.spec`：PyInstaller 配置。
- `packaging/EyesProtect.iss`：Inno Setup 安装包配置。
- `VERSION`：当前发行版本号，发布新版时请同步更新 `packaging/EyesProtect.iss` 里的 `MyAppVersion`。

`packaged_app.py` 会给桌面伴侣进程注入 `EYES_PROTECT_API_BASE_URL` 和 `EYES_PROTECT_API_URL`。如果后续修改 `desktop_reminder.py`，请优先从这两个环境变量读取后端地址，再回退到 `http://127.0.0.1:8000/api`。

安装包版本下，前端和 API 是同源访问，推荐前端请求统一使用相对路径 `/api/...`。如果前端写死了 `http://127.0.0.1:8000/api`，默认端口下仍可工作，但以后调整端口会更不灵活。

## 构建要求

在打包机器上安装：

- Python 3.11+
- Node.js
- Inno Setup 6，可选；没有它也能先生成 `dist\EyesProtect\EyesProtect.exe` 应用目录

## 构建命令

在项目根目录运行：

```powershell
.\packaging\build_windows.ps1
```

构建前也可以先手动验证打包入口：

```powershell
cd frontend
npm install
npm run build
cd ..
python packaged_app.py
```

运行后会打开浏览器页面，API 和页面都来自本机 `127.0.0.1:8000`，SQLite 数据会写到 `%APPDATA%\EyesProtect\eyes_protect.db`。

首版安装版没有系统托盘。关闭浏览器页面后，本地提醒进程仍可能继续运行，以保证桌面提醒有效；如果要做成更完整的普通用户产品，下一步建议增加系统托盘和退出菜单。

脚本会依次执行：

1. 安装并构建 Vue 前端。
2. 创建 `.packaging-venv`。
3. 安装后端依赖和 PyInstaller。
4. 生成 `dist\EyesProtect` 应用目录。
5. 如果安装了 Inno Setup，生成 `dist\installer\EyesProtect-Setup-0.1.0.exe`。

## 安装与升级

用户运行安装包即可安装。后续发布新版本时，重新构建安装包并覆盖安装即可。程序文件会更新，用户设置和 SQLite 数据会继续保留在 `%APPDATA%\EyesProtect`。

## 开发模式

原来的开发启动方式仍然保留：

```powershell
.\start.ps1
```

安装包入口只用于面向非程序员用户的本地桌面发行版本。
