from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.export_service import (
    export_video_to_obsidian,
    export_up_videos_to_obsidian,
    generate_daily_summary,
    export_favorite_video_to_obsidian,
)

router = APIRouter()


@router.post("/obsidian/{video_id}")
async def export_obsidian_video(video_id: int, db: AsyncSession = Depends(get_db)):
    """导出单个已分析视频为 Obsidian Markdown 文件"""
    result = await export_video_to_obsidian(video_id, db)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["msg"])
    return result


@router.post("/obsidian/up/{up_id}")
async def export_obsidian_up(up_id: int, db: AsyncSession = Depends(get_db)):
    """批量导出 UP 主全部已分析视频"""
    result = await export_up_videos_to_obsidian(up_id, db)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["msg"])
    return result


@router.post("/daily")
async def export_daily(target_date: str = None, db: AsyncSession = Depends(get_db)):
    """生成指定日期汇总日报（默认昨日），格式 YYYY-MM-DD"""
    date_obj = None
    if target_date:
        try:
            date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD")
    result = await generate_daily_summary(db, target_date=date_obj)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["msg"])
    return result


@router.post("/obsidian/favorite/{video_id}")
async def export_obsidian_favorite(video_id: int, db: AsyncSession = Depends(get_db)):
    """导出单个已分析收藏视频为 Obsidian Markdown 文件"""
    result = await export_favorite_video_to_obsidian(video_id, db)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["msg"])
    return result
