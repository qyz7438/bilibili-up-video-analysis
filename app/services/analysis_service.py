from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Video, Analysis, FavoriteVideo, FavoriteAnalysis
from app.services.llm_service import analyze_content
from app.config import settings


async def analyze_video_by_id(video_id: int, db: AsyncSession) -> dict:
    """分析单个视频的内容（要求视频已有字幕）"""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        return {"success": False, "msg": "视频不存在"}

    if not video.subtitle_content or len(video.subtitle_content.strip()) < 10:
        return {"success": False, "msg": "视频无字幕或字幕太短，无法分析"}

    # 检查是否已有分析结果
    result = await db.execute(select(Analysis).where(Analysis.video_id == video_id))
    existing = result.scalar_one_or_none()

    print(f"[Analysis] 开始分析视频: {video.bvid} - {video.title}")
    analysis_data = await analyze_content(video.subtitle_content)
    if existing:
        existing.summary = analysis_data.get("summary", "")
        existing.key_points = ", ".join(analysis_data.get("key_points", []))
        existing.topics = ", ".join(analysis_data.get("topics", []))
        existing.sentiment = analysis_data.get("sentiment", "中性")
        existing.llm_model = settings.LLM_MODEL
    else:
        analysis = Analysis(
            video_id=video_id,
            summary=analysis_data.get("summary", ""),
            key_points=", ".join(analysis_data.get("key_points", [])),
            topics=", ".join(analysis_data.get("topics", [])),
            sentiment=analysis_data.get("sentiment", "中性"),
            llm_model=settings.LLM_MODEL,
        )
        db.add(analysis)

    await db.commit()
    print(f"[Analysis] 分析完成: {video.bvid}")
    return {"success": True, "msg": "分析完成"}


async def analyze_up_all(up_id: int, db: AsyncSession) -> dict:
    """批量分析UP主所有带字幕但未分析的视频"""
    from sqlalchemy import and_
    result = await db.execute(
        select(Video).where(
            and_(
                Video.up_id == up_id,
                Video.subtitle_content.isnot(None),
                Video.subtitle_content != ""
            )
        )
    )
    videos = result.scalars().all()

    analyzed = 0
    skipped = 0
    for video in videos:
        # 检查是否已有分析
        res = await db.execute(select(Analysis).where(Analysis.video_id == video.id))
        if res.scalar_one_or_none():
            skipped += 1
            continue

        await analyze_video_by_id(video.id, db)
        analyzed += 1

    return {
        "success": True,
        "msg": f"批量分析完成：新增分析 {analyzed} 个，跳过已分析 {skipped} 个"
    }


async def analyze_favorite_video_by_id(video_id: int, db: AsyncSession) -> dict:
    """分析单个收藏视频的内容"""
    result = await db.execute(select(FavoriteVideo).where(FavoriteVideo.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        return {"success": False, "msg": "视频不存在"}

    if not video.subtitle_content or len(video.subtitle_content.strip()) < 10:
        return {"success": False, "msg": "视频无字幕或字幕太短，无法分析"}

    check = await db.execute(select(FavoriteAnalysis).where(FavoriteAnalysis.video_id == video_id))
    existing = check.scalar_one_or_none()

    print(f"[FavoriteAnalysis] 开始分析收藏视频: {video.bvid} - {video.title}")
    analysis_data = await analyze_content(video.subtitle_content)

    if existing:
        existing.summary = analysis_data.get("summary", "")
        existing.key_points = ", ".join(analysis_data.get("key_points", []))
        existing.topics = ", ".join(analysis_data.get("topics", []))
        existing.sentiment = analysis_data.get("sentiment", "中性")
        existing.llm_model = settings.LLM_MODEL
    else:
        analysis = FavoriteAnalysis(
            video_id=video_id,
            summary=analysis_data.get("summary", ""),
            key_points=", ".join(analysis_data.get("key_points", [])),
            topics=", ".join(analysis_data.get("topics", [])),
            sentiment=analysis_data.get("sentiment", "中性"),
            llm_model=settings.LLM_MODEL,
        )
        db.add(analysis)

    await db.commit()
    print(f"[FavoriteAnalysis] 分析完成: {video.bvid}")
    return {"success": True, "msg": "分析完成"}


async def analyze_favorite_all(db: AsyncSession) -> dict:
    """批量分析所有有字幕但未分析的收藏视频"""
    result = await db.execute(
        select(FavoriteVideo).where(
            FavoriteVideo.subtitle_content.isnot(None),
            FavoriteVideo.subtitle_content != ""
        )
    )
    videos = result.scalars().all()

    analyzed = 0
    skipped = 0
    for video in videos:
        res = await db.execute(select(FavoriteAnalysis).where(FavoriteAnalysis.video_id == video.id))
        if res.scalar_one_or_none():
            skipped += 1
            continue

        await analyze_favorite_video_by_id(video.id, db)
        analyzed += 1

    return {
        "success": True,
        "msg": f"批量分析完成：新增分析 {analyzed} 个，跳过已分析 {skipped} 个"
    }
