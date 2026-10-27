import pytest
import os
import sys

# 确保能 import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base, Up, Video, Analysis, FavoriteVideo, FavoriteAnalysis
from app.services.export_service import (
    export_video_to_obsidian,
    export_up_videos_to_obsidian,
    generate_daily_summary,
    export_favorite_video_to_obsidian,
    _sanitize_filename,
)

DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.fixture
async def sample_data(db):
    """创建测试数据"""
    up = Up(uid="12345", name="测试UP主", face="", description="")
    db.add(up)
    await db.commit()
    await db.refresh(up)

    video = Video(
        bvid="BV1test1234",
        aid="1234",
        title="测试视频标题",
        description="测试描述",
        pic="",
        pubdate=datetime(2024, 5, 10, 10, 0, 0, tzinfo=timezone.utc),
        up_id=up.id,
        subtitle_content="测试字幕内容",
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    analysis = Analysis(
        video_id=video.id,
        summary="这是一个测试视频的摘要。",
        key_points="要点1, 要点2, 要点3",
        topics="测试, 演示",
        sentiment="正面",
        llm_model="moonshot-v1-8k",
    )
    db.add(analysis)
    await db.commit()

    return {"up": up, "video": video, "analysis": analysis}


@pytest.mark.asyncio
async def test_sanitize_filename():
    assert _sanitize_filename("正常名称") == "正常名称"
    assert _sanitize_filename("非法/字符:test") == "非法_字符_test"
    assert _sanitize_filename("") == "unknown"
    assert _sanitize_filename("   ") == "unknown"


@pytest.mark.asyncio
async def test_export_video_to_obsidian(db, sample_data):
    video = sample_data["video"]
    result = await export_video_to_obsidian(video.id, db)
    assert result["success"] is True
    assert "file_path" in result
    assert os.path.exists(result["file_path"])

    with open(result["file_path"], "r", encoding="utf-8") as f:
        content = f.read()
    assert "测试视频标题" in content
    assert "BV1test1234" in content
    assert "这是一个测试视频的摘要" in content
    assert "要点1" in content
    assert "正面" in content
    assert "tags:" in content


@pytest.mark.asyncio
async def test_export_up_videos_to_obsidian(db, sample_data):
    up = sample_data["up"]
    result = await export_up_videos_to_obsidian(up.id, db)
    assert result["success"] is True
    assert result["exported"] == 1
    assert len(result["files"]) == 1
    assert os.path.exists(result["files"][0])


@pytest.mark.asyncio
async def test_generate_daily_summary(db, sample_data):
    # 使用测试记录的创建日期，避免依赖当前日期和默认的昨日逻辑。
    result = await generate_daily_summary(db, target_date=sample_data["analysis"].created_at)
    assert result["success"] is True
    assert "file_path" in result
    assert os.path.exists(result["file_path"])

    with open(result["file_path"], "r", encoding="utf-8") as f:
        content = f.read()
    assert "视频分析日报" in content
    assert "测试UP主" in content
    assert "测试视频标题" in content


@pytest.mark.asyncio
async def test_generate_daily_summary_defaults_to_yesterday(db, sample_data):
    sample_data["analysis"].created_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()
    result = await generate_daily_summary(db)
    assert result["success"] is True
    assert result["video_count"] == 1


@pytest.mark.asyncio
async def test_export_video_not_found(db):
    result = await export_video_to_obsidian(99999, db)
    assert result["success"] is False
    assert "不存在" in result["msg"]


@pytest.mark.asyncio
async def test_export_up_not_found(db):
    result = await export_up_videos_to_obsidian(99999, db)
    assert result["success"] is False
    assert "UP主不存在" in result["msg"]


@pytest.mark.asyncio
async def test_export_favorite_video_to_obsidian(db):
    fav = FavoriteVideo(
        bvid="BVfav12345",
        title="收藏视频标题",
        cover="",
        intro="",
        duration=120,
        uploader_name="收藏UP",
        uploader_mid="999",
        fav_time=datetime.now(timezone.utc),
        pubtime=datetime.now(timezone.utc),
        subtitle_content="收藏字幕",
    )
    db.add(fav)
    await db.commit()
    await db.refresh(fav)

    fav_analysis = FavoriteAnalysis(
        video_id=fav.id,
        summary="收藏视频摘要",
        key_points="收藏要点1",
        topics="收藏主题",
        sentiment="中性",
        llm_model="moonshot-v1-8k",
    )
    db.add(fav_analysis)
    await db.commit()

    result = await export_favorite_video_to_obsidian(fav.id, db)
    assert result["success"] is True
    assert os.path.exists(result["file_path"])

    with open(result["file_path"], "r", encoding="utf-8") as f:
        content = f.read()
    assert "收藏视频标题" in content
    assert "BVfav12345" in content
    assert "收藏视频摘要" in content
