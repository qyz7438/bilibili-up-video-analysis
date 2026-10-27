from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import Analysis, Video
from app.services.analysis_service import analyze_video_by_id, analyze_up_all

router = APIRouter()


@router.post("/analyze/{video_id}")
async def analyze_video(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await analyze_video_by_id(video_id, db)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["msg"])
    return result


@router.post("/analyze_up/{up_id}")
async def analyze_up(up_id: int, db: AsyncSession = Depends(get_db)):
    result = await analyze_up_all(up_id, db)
    return result


@router.get("/{video_id}")
async def get_analysis(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Analysis).where(Analysis.video_id == video_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        return {"success": True, "data": None}

    return {
        "success": True,
        "data": {
            "id": analysis.id,
            "summary": analysis.summary,
            "key_points": [kp.strip() for kp in analysis.key_points.split(",") if kp.strip()] if analysis.key_points else [],
            "topics": [t.strip() for t in analysis.topics.split(",") if t.strip()] if analysis.topics else [],
            "sentiment": analysis.sentiment,
            "llm_model": analysis.llm_model,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        }
    }


@router.get("/stats/{up_id}")
async def get_stats(up_id: int, db: AsyncSession = Depends(get_db)):
    # 总视频数
    total_result = await db.execute(select(func.count()).select_from(Video).where(Video.up_id == up_id))
    total_videos = total_result.scalar()

    # 已分析数
    analyzed_result = await db.execute(
        select(func.count()).select_from(Analysis)
        .join(Video, Analysis.video_id == Video.id)
        .where(Video.up_id == up_id)
    )
    analyzed_count = analyzed_result.scalar()

    # 主题分布（简单聚合）
    topic_result = await db.execute(
        select(Analysis.topics)
        .join(Video, Analysis.video_id == Video.id)
        .where(Video.up_id == up_id)
    )
    topic_map = {}
    for row in topic_result.scalars().all():
        if row:
            for t in row.split(","):
                t = t.strip()
                if t:
                    topic_map[t] = topic_map.get(t, 0) + 1

    return {
        "success": True,
        "data": {
            "total_videos": total_videos,
            "analyzed_count": analyzed_count,
            "topic_distribution": topic_map
        }
    }
