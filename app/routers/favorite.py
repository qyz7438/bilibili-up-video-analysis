from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from app.database import get_db
from app.models import FavoriteVideo, FavoriteAnalysis
from app.services.bilibili_service import fetch_favorite_folders, fetch_favorite_videos, fetch_video_subtitle
from app.services.transcribe_service import transcribe_video_audio
from app.services.analysis_service import analyze_favorite_video_by_id, analyze_favorite_all

router = APIRouter()


class SyncBody(BaseModel):
    uid: str
    media_id: int


@router.get("/folders")
async def get_folders(uid: str = Query(..., description="B站用户UID")):
    if not uid.isdigit():
        raise HTTPException(status_code=400, detail="UID必须是数字")
    folders = await fetch_favorite_folders(uid)
    return {"success": True, "data": folders}


@router.post("/sync")
async def sync_favorites(body: SyncBody, db: AsyncSession = Depends(get_db)):
    uid = body.uid
    media_id = body.media_id

    if not uid or not uid.isdigit():
        raise HTTPException(status_code=400, detail="UID必须是数字")
    if not media_id:
        raise HTTPException(status_code=400, detail="media_id不能为空")

    added = 0
    pn = 1
    MAX_PAGES = 50
    while pn <= MAX_PAGES:
        videos, has_more = await fetch_favorite_videos(media_id, pn=pn, ps=20)
        for v in videos:
            bvid = v.get("bvid", "")
            if not bvid:
                continue
            existing = await db.execute(select(FavoriteVideo).where(FavoriteVideo.bvid == bvid))
            if existing.scalar_one_or_none():
                continue
            fav = FavoriteVideo(**v)
            db.add(fav)
            added += 1

        if not has_more:
            break
        pn += 1

    await db.commit()
    return {"success": True, "msg": f"同步完成，新增 {added} 个视频"}


@router.get("/list")
async def list_favorites(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    count_result = await db.execute(select(func.count()).select_from(FavoriteVideo))
    total = count_result.scalar()

    result = await db.execute(
        select(FavoriteVideo)
        .order_by(FavoriteVideo.fav_time.desc().nullslast())
        .offset((page - 1) * size)
        .limit(size)
    )
    videos = result.scalars().all()

    video_ids = [v.id for v in videos]
    analysis_result = await db.execute(
        select(FavoriteAnalysis).where(FavoriteAnalysis.video_id.in_(video_ids))
    )
    analyzed_ids = {a.video_id for a in analysis_result.scalars().all()}

    items = []
    for v in videos:
        has_subtitle = bool(v.subtitle_content and len(v.subtitle_content.strip()) > 10)
        items.append({
            "id": v.id,
            "bvid": v.bvid,
            "title": v.title,
            "cover": v.cover,
            "uploader_name": v.uploader_name,
            "duration": v.duration,
            "fav_time": v.fav_time.isoformat() if v.fav_time else None,
            "has_subtitle": has_subtitle,
            "is_analyzed": v.id in analyzed_ids,
        })

    return {
        "success": True,
        "total": total,
        "page": page,
        "size": size,
        "items": items
    }


@router.post("/subtitle/{video_id}")
async def fetch_favorite_subtitle(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FavoriteVideo).where(FavoriteVideo.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    content = await fetch_video_subtitle(video.bvid)
    video.subtitle_content = content
    await db.commit()

    if content:
        return {"success": True, "msg": f"字幕获取成功，共 {len(content)} 字符", "content": content}
    else:
        return {"success": False, "msg": "该视频暂无CC字幕"}


@router.post("/transcribe/{video_id}")
async def transcribe_favorite(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FavoriteVideo).where(FavoriteVideo.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    if video.subtitle_content and len(video.subtitle_content.strip()) > 10:
        return {"success": True, "msg": "该视频已有字幕，跳过转录", "content": video.subtitle_content}

    text = await transcribe_video_audio(video.bvid)
    if text:
        video.subtitle_content = text
        await db.commit()
        return {"success": True, "msg": f"音频转录成功，共 {len(text)} 字符", "content": text}
    else:
        return {"success": False, "msg": "音频转录失败，可能未配置API Key或视频无音频"}


@router.post("/subtitle_all")
async def fetch_all_favorite_subtitles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FavoriteVideo).where(FavoriteVideo.subtitle_content.is_(None))
    )
    videos = result.scalars().all()

    success = 0
    failed = 0
    for video in videos:
        content = await fetch_video_subtitle(video.bvid)
        if content:
            video.subtitle_content = content
            success += 1
        else:
            failed += 1

    await db.commit()
    return {"success": True, "msg": f"批量获取字幕完成：成功 {success} 个，失败/无字幕 {failed} 个"}


@router.post("/transcribe_all")
async def transcribe_all_favorites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FavoriteVideo).where(FavoriteVideo.subtitle_content.is_(None))
    )
    videos = result.scalars().all()

    success = 0
    failed = 0
    for video in videos:
        text = await transcribe_video_audio(video.bvid)
        if text:
            video.subtitle_content = text
            success += 1
        else:
            failed += 1

    await db.commit()
    return {"success": True, "msg": f"批量转录完成：成功 {success} 个，失败 {failed} 个"}


@router.post("/analyze/{video_id}")
async def analyze_favorite(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await analyze_favorite_video_by_id(video_id, db)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["msg"])
    return result


@router.post("/analyze_all")
async def analyze_all_favorites(db: AsyncSession = Depends(get_db)):
    result = await analyze_favorite_all(db)
    return result


@router.get("/analysis/{video_id}")
async def get_favorite_analysis(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FavoriteAnalysis).where(FavoriteAnalysis.video_id == video_id))
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


@router.get("/stats")
async def get_favorite_stats(db: AsyncSession = Depends(get_db)):
    total_result = await db.execute(select(func.count()).select_from(FavoriteVideo))
    total_videos = total_result.scalar()

    analyzed_result = await db.execute(select(func.count()).select_from(FavoriteAnalysis))
    analyzed_count = analyzed_result.scalar()

    topic_result = await db.execute(select(FavoriteAnalysis.topics))
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


@router.delete("/{video_id}")
async def delete_favorite(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FavoriteVideo).where(FavoriteVideo.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    await db.delete(video)
    await db.commit()
    return {"success": True, "msg": "删除成功"}
