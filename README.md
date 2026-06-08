# 护眼提醒

一个本地 Web 护眼提醒小工具。后端使用 FastAPI + SQLite，前端使用 Vue + Vite。

## 功能

- 自定义提醒间隔、休息时长和稍后提醒时长，休息时长支持分钟或秒。
- 配置持久化到 SQLite。
- 页面内强提醒：全屏遮罩、循环声音、标题闪烁、浏览器通知。
- 支持启动、暂停、重置、开始休息、稍后提醒、跳过本次。

## 启动

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

打开 Vite 输出的本地地址，通常是 `http://127.0.0.1:5173`。

## 测试

```bash
cd backend
pytest
```
