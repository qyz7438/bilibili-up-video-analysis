from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models import Video, Up, Analysis
from app.services.bilibili_service import fetch_up_videos, fetch_video_subtitle
from app.services.transcribe_service import transcribe_video_audio

router = APIRouter()


@router.post("/sync/{up_id}")
async def sync_videos(up_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Up).where(Up.id == up_id))
    up = result.scalar_one_or_none()
    if not up:
        raise HTTPException(status_code=404, detail="UP主不存在")

    videos = await fetch_up_videos(up.uid, pn=1, ps=50)
    added = 0
    for v in videos:
        if not v.get("bvid"):
            continue
        res = await db.execute(select(Video).where(Video.bvid == v["bvid"]))
        if res.scalar_one_or_none():
            continue
        video = Video(up_id=up_id, **v)
        db.add(video)
        added += 1

    await db.commit()
    return {"success": True, "msg": f"同步完成，新增 {added} 个视频"}


@router.get("/list")
async def list_videos(
    up_id: int = Query(..., description="UP主ID"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    # 统计总数
    count_result = await db.execute(select(func.count()).select_from(Video).where(Video.up_id == up_id))
    total = count_result.scalar()

    # 分页查询
    result = await db.execute(
        select(Video).where(Video.up_id == up_id)
        .order_by(Video.pubdate.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    videos = result.scalars().all()

    # 查询哪些视频已有分析结果
    video_ids = [v.id for v in videos]
    analysis_result = await db.execute(select(Analysis).where(Analysis.video_id.in_(video_ids)))
    analyzed_ids = {a.video_id for a in analysis_result.scalars().all()}

    items = []
    for v in videos:
        has_subtitle = bool(v.subtitle_content and len(v.subtitle_content.strip()) > 10)
        items.append({
            "id": v.id,
            "bvid": v.bvid,
            "title": v.title,
            "pic": v.pic,
            "pubdate": v.pubdate.isoformat() if v.pubdate else None,
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
async def fetch_subtitle(video_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
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
async def transcribe_video(video_id: int, db: AsyncSession = Depends(get_db)):
    """对无CC字幕的视频进行音频下载+Whisper转录"""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    # 如果已有字幕，跳过
    if video.subtitle_content and len(video.subtitle_content.strip()) > 10:
        return {"success": True, "msg": "该视频已有字幕，跳过转录", "content": video.subtitle_content}

    text = await transcribe_video_audio(video.bvid)
    if text:
        video.subtitle_content = text
        await db.commit()
        return {"success": True, "msg": f"音频转录成功，共 {len(text)} 字符", "content": text}
    else:
        return {"success": False, "msg": "音频转录失败，可能未配置API Key或视频无音频"}


@router.post("/transcribe_all/{up_id}")
async def transcribe_all(up_id: int, db: AsyncSession = Depends(get_db)):
    """批量转录UP主所有无字幕视频"""
    from sqlalchemy import and_
    result = await db.execute(
        select(Video).where(
            and_(
                Video.up_id == up_id,
                Video.subtitle_content.is_(None)
            )
        )
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


@router.post("/subtitle_all/{up_id}")
async def fetch_all_subtitles(up_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video).where(
            and_(
                Video.up_id == up_id,
                Video.subtitle_content.is_(None)
            )
        )
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
