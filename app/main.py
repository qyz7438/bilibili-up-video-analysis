import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.database import init_db
from app.routers import up, video, analysis, favorite, export

app = FastAPI(title="B站UP主视频AI分析系统", version="1.0.0")


@app.on_event("startup")
async def startup():
    os.makedirs("data", exist_ok=True)
    await init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index():
    try:
        with open("app/templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Frontend not found</h1>"


app.include_router(up.router, prefix="/api/up", tags=["UP主管理"])
app.include_router(video.router, prefix="/api/video", tags=["视频管理"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["分析管理"])
app.include_router(favorite.router, prefix="/api/favorite", tags=["收藏夹管理"])
app.include_router(export.router, prefix="/api/export", tags=["导出管理"])
