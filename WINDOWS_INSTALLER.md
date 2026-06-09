# Windows 安装包发行说明

本项目可以做成面向普通用户的 Windows 本地安装包。安装后用户不需要安装 Python、Node.js，也不需要运行命令行。

## 用户体验

用户只需要：

1. 双击 `EyesProtect-Setup-版本号.exe` 安装。
2. 从桌面或开始菜单打开 EyesProtect。
3. 在页面中设置提醒间隔、休息时长、声音提醒、桌面伴侣和请勿打扰时段。

应用内部仍然是 FastAPI + Vue + SQLite，但这些都运行在用户自己的电脑上，不需要远程服务器。

首版安装包启动后会在后台保持本地提醒服务和桌面伴侣运行。关闭浏览器页面不一定代表退出程序，因为这样才能在页面关闭后继续提醒。后续可以再补系统托盘菜单，提供“打开面板 / 暂停提醒 / 退出程序”。

## 数据保存位置

安装包版本会把 SQLite 数据库保存到：

```text
%APPDATA%\EyesProtect\eyes_protect.db
```

这样后续覆盖安装新版时，用户配置和历史数据不会丢。

## 构建安装包

构建机需要安装：

- Python 3.11+
- Node.js
- Inno Setup 6

在项目根目录运行：

```powershell
.\build_windows_installer.ps1
```

生成结果：

- PyInstaller 应用目录：`dist\EyesProtect`
- Inno Setup 安装包：`dist\installer\EyesProtect-Setup-0.1.0.exe`

如果没有安装 Inno Setup，脚本仍会生成 `dist\EyesProtect`，只是不会生成安装包。

## 后续更新

代码、界面或功能改动后，需要重新构建一个新安装包。用户可以直接覆盖安装，新版本会替换程序文件，但保留 `%APPDATA%\EyesProtect` 下的数据。

发布新版前，请同步更新根目录 `VERSION` 和 `packaging\EyesProtect.iss` 里的 `MyAppVersion`。
