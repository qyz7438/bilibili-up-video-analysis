import os
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.models import Video, Analysis, Up, FavoriteVideo, FavoriteAnalysis


def _sanitize_filename(name: str) -> str:
    """去除文件名中的非法字符"""
    if not name:
        return "unknown"
    # 替换 Windows/Linux 非法字符
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    # 去除首尾空白
    name = name.strip()
    # 限制长度
    return name[:100] or "unknown"


def _build_obsidian_md(video, analysis) -> str:
    """构建 Obsidian 格式的 Markdown 内容"""
    up_name = video.up.name if hasattr(video, "up") and video.up else "unknown"
    title = video.title or "无标题"
    bvid = video.bvid or ""
    url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
    pubdate = video.pubdate
    date_str = pubdate.strftime("%Y-%m-%d") if pubdate else ""

    sentiment = analysis.sentiment or "中性"
    topics = []
    if analysis.topics:
        topics = [t.strip() for t in analysis.topics.split(",") if t.strip()]
    tags = topics + ["bilibili", "视频分析"]
    tags_str = ", ".join([f'"{t}"' for t in tags])

    key_points = []
    if analysis.key_points:
        key_points = [kp.strip() for kp in analysis.key_points.split(",") if kp.strip()]

    summary = analysis.summary or "暂无摘要"

    lines = [
        "---",
        f'title: "{_escape_yaml(title)}"',
        f"bvid: {bvid}",
        f'up: "{_escape_yaml(up_name)}"',
        f"url: {url}",
        f"date: {date_str}",
        f"tags: [{tags_str}]",
        f'sentiment: "{sentiment}"',
        "---",
        "",
        f"# {title}",
        "",
        f"> B站链接: [{url}]({url})",
        "",
        "## 摘要",
        "",
        summary,
        "",
        "## 关键要点",
        "",
    ]
    for kp in key_points:
        lines.append(f"- {kp}")
    lines.append("")

    return "\n".join(lines)


def _escape_yaml(value: str) -> str:
    """转义 YAML 字符串中的特殊字符"""
    if not value:
        return ""
    # 如果包含双引号或特殊字符，进行转义
    if '"' in value:
        value = value.replace('"', '\\"')
    return value


async def export_video_to_obsidian(video_id: int, db: AsyncSession) -> dict:
    """导出单个已分析视频为 Obsidian Markdown 文件"""
    result = await db.execute(
        select(Video, Analysis)
        .join(Analysis, Video.id == Analysis.video_id)
        .where(Video.id == video_id)
    )
    row = result.first()
    if not row:
        return {"success": False, "msg": "视频不存在或未分析"}

    video, analysis = row
    up_name = video.up.name if video.up else "unknown"
    safe_up_name = _sanitize_filename(up_name)
    bvid = video.bvid or "unknown"

    output_dir = os.path.join("data", "obsidian", safe_up_name)
    os.makedirs(output_dir, exist_ok=True)

    file_path = os.path.join(output_dir, f"{bvid}.md")
    content = _build_obsidian_md(video, analysis)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "success": True,
        "msg": "导出成功",
        "file_path": file_path,
    }


async def export_up_videos_to_obsidian(up_id: int, db: AsyncSession) -> dict:
    """批量导出 UP 主全部已分析视频"""
    result = await db.execute(select(Up).where(Up.id == up_id))
    up = result.scalar_one_or_none()
    if not up:
        return {"success": False, "msg": "UP主不存在"}

    result = await db.execute(
        select(Video, Analysis)
        .join(Analysis, Video.id == Analysis.video_id)
        .where(Video.up_id == up_id)
    )
    rows = result.all()

    if not rows:
        return {"success": True, "msg": "该UP主暂无已分析的视频", "exported": 0, "files": []}

    safe_up_name = _sanitize_filename(up.name)
    output_dir = os.path.join("data", "obsidian", safe_up_name)
    os.makedirs(output_dir, exist_ok=True)

    exported_files = []
    for video, analysis in rows:
        bvid = video.bvid or "unknown"
        file_path = os.path.join(output_dir, f"{bvid}.md")
        content = _build_obsidian_md(video, analysis)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        exported_files.append(file_path)

    return {
        "success": True,
        "msg": f"批量导出完成，共 {len(exported_files)} 个视频",
        "exported": len(exported_files),
        "files": exported_files,
    }


async def generate_daily_summary(db: AsyncSession, target_date: datetime = None) -> dict:
    """生成每日总结文档，汇总 target_date 当天的分析结果（默认昨日）"""
    if target_date is None:
        target_date = datetime.now(timezone.utc) - timedelta(days=1)

    # 计算当天的起止时间
    start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    # 查询当天有分析结果的视频（按 created_at 或 analysis.created_at）
    result = await db.execute(
        select(Video, Analysis, Up)
        .join(Analysis, Video.id == Analysis.video_id)
        .join(Up, Video.up_id == Up.id)
        .where(
            and_(
                Analysis.created_at >= start,
                Analysis.created_at < end,
            )
        )
        .order_by(Up.name, Video.pubdate.desc())
    )
    rows = result.all()

    date_str = start.strftime("%Y-%m-%d")
    output_dir = os.path.join("data", "daily")
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{date_str}_summary.md")

    if not rows:
        content = f"# {date_str} 视频分析日报\n\n今日暂无新增分析结果。\n"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "msg": "今日暂无新增分析结果",
            "file_path": file_path,
            "video_count": 0,
        }

    # 按 UP 主分组
    up_groups = {}
    for video, analysis, up in rows:
        up_name = up.name or "未知UP主"
        if up_name not in up_groups:
            up_groups[up_name] = []
        up_groups[up_name].append((video, analysis))

    lines = [
        f"# {date_str} 视频分析日报",
        "",
        f"- 日期: {date_str}",
        f"- 视频总数: {len(rows)}",
        "",
    ]

    for up_name, items in up_groups.items():
        lines.append(f"## {up_name}")
        lines.append("")
        for video, analysis in items:
            bvid = video.bvid or ""
            url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
            title = video.title or "无标题"
            summary = analysis.summary or "暂无摘要"
            sentiment = analysis.sentiment or "中性"
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"- BV号: `{bvid}`")
            lines.append(f"- 链接: [{url}]({url})")
            lines.append(f"- 情感: {sentiment}")
            lines.append("")
            lines.append(f"{summary}")
            lines.append("")

    content = "\n".join(lines)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "success": True,
        "msg": f"日报生成成功，共 {len(rows)} 个视频",
        "file_path": file_path,
        "video_count": len(rows),
    }


def _build_favorite_obsidian_md(video: FavoriteVideo, analysis: FavoriteAnalysis) -> str:
    """构建收藏视频 Obsidian Markdown 内容（公开工具函数）"""
    title = video.title or "无标题"
    bvid = video.bvid or ""
    url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
    pubdate = video.pubtime
    date_str = pubdate.strftime("%Y-%m-%d") if pubdate else ""
    up_name = video.uploader_name or "unknown"
    sentiment = analysis.sentiment or "中性"
    topics = []
    if analysis.topics:
        topics = [t.strip() for t in analysis.topics.split(",") if t.strip()]
    tags = topics + ["bilibili", "收藏视频", "视频分析"]
    tags_str = ", ".join([f'"{t}"' for t in tags])
    key_points = []
    if analysis.key_points:
        key_points = [kp.strip() for kp in analysis.key_points.split(",") if kp.strip()]
    summary = analysis.summary or "暂无摘要"

    lines = [
        "---",
        f'title: "{_escape_yaml(title)}"',
        f"bvid: {bvid}",
        f'up: "{_escape_yaml(up_name)}"',
        f"url: {url}",
        f"date: {date_str}",
        f"tags: [{tags_str}]",
        f'sentiment: "{sentiment}"',
        "---",
        "",
        f"# {title}",
        "",
        f"> B站链接: [{url}]({url})",
        "",
        "## 摘要",
        "",
        summary,
        "",
        "## 关键要点",
        "",
    ]
    for kp in key_points:
        lines.append(f"- {kp}")
    lines.append("")

    return "\n".join(lines)


async def export_favorite_video_to_obsidian(video_id: int, db: AsyncSession) -> dict:
    """导出单个已分析收藏视频为 Obsidian Markdown 文件"""
    result = await db.execute(
        select(FavoriteVideo, FavoriteAnalysis)
        .join(FavoriteAnalysis, FavoriteVideo.id == FavoriteAnalysis.video_id)
        .where(FavoriteVideo.id == video_id)
    )
    row = result.first()
    if not row:
        return {"success": False, "msg": "收藏视频不存在或未分析"}

    video, analysis = row
    up_name = video.uploader_name or "unknown"
    safe_up_name = _sanitize_filename(up_name)
    bvid = video.bvid or "unknown"

    output_dir = os.path.join("data", "obsidian", "favorites", safe_up_name)
    os.makedirs(output_dir, exist_ok=True)

    file_path = os.path.join(output_dir, f"{bvid}.md")
    content = _build_favorite_obsidian_md(video, analysis)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "success": True,
        "msg": "导出成功",
        "file_path": file_path,
    }


async def export_favorite_to_path(video_id: int, output_path: str, db: AsyncSession) -> dict:
    """导出单个已分析收藏视频到指定路径"""
    result = await db.execute(
        select(FavoriteVideo, FavoriteAnalysis)
        .join(FavoriteAnalysis, FavoriteVideo.id == FavoriteAnalysis.video_id)
        .where(FavoriteVideo.id == video_id)
    )
    row = result.first()
    if not row:
        return {"success": False, "msg": "收藏视频不存在或未分析"}

    video, analysis = row
    content = _build_favorite_obsidian_md(video, analysis)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "success": True,
        "msg": "导出成功",
        "file_path": output_path,
    }


async def export_all_favorites_to_dir(output_dir: str, db: AsyncSession) -> dict:
    """批量导出所有已分析收藏视频到指定目录（如llm-wiki _inbox/）"""
    result = await db.execute(
        select(FavoriteVideo, FavoriteAnalysis)
        .join(FavoriteAnalysis, FavoriteVideo.id == FavoriteAnalysis.video_id)
    )
    rows = result.all()

    if not rows:
        return {"success": True, "exported": 0, "files": []}

    os.makedirs(output_dir, exist_ok=True)
    exported_files = []
    for video, analysis in rows:
        bvid = video.bvid or "unknown"
        file_path = os.path.join(output_dir, f"{bvid}.md")
        content = _build_favorite_obsidian_md(video, analysis)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        exported_files.append(file_path)

    return {
        "success": True,
        "msg": f"导出完成，共 {len(exported_files)} 个视频",
        "exported": len(exported_files),
        "files": exported_files,
    }
