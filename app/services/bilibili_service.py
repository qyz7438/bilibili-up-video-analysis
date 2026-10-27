import aiohttp
from datetime import datetime, timezone
from bilibili_api import user, video
from app.config import settings


def _get_bilibili_cookies() -> dict:
    """构建B站Cookie字典，用于需要登录态的API请求"""
    cookies = {}
    if settings.BILIBILI_SESSDATA:
        cookies["SESSDATA"] = settings.BILIBILI_SESSDATA
    if settings.BILIBILI_BILI_JCT:
        cookies["bili_jct"] = settings.BILIBILI_BILI_JCT
    if settings.BILIBILI_BUVID3:
        cookies["buvid3"] = settings.BILIBILI_BUVID3
    return cookies


async def fetch_up_info(uid: str) -> dict:
    """获取B站UP主信息"""
    try:
        u = user.User(uid=int(uid))
        info = await u.get_user_info()
        return {
            "uid": str(uid),
            "name": info.get("name", ""),
            "face": info.get("face", ""),
            "description": info.get("sign", ""),
        }
    except Exception as e:
        print(f"[fetch_up_info] 获取UP主信息失败 uid={uid}: {e}")
        return {
            "uid": str(uid),
            "name": "",
            "face": "",
            "description": "",
        }


async def fetch_up_videos(uid: str, pn: int = 1, ps: int = 30) -> list[dict]:
    """获取B站UP主的视频列表"""
    try:
        u = user.User(uid=int(uid))
        resp = await u.get_videos(pn=pn, ps=ps)

        # 处理常见嵌套结构
        videos = []
        if isinstance(resp, dict):
            if "list" in resp and isinstance(resp["list"], dict):
                videos = resp["list"].get("vlist", []) or resp["list"].get("list", [])
            elif "list" in resp and isinstance(resp["list"], list):
                videos = resp["list"]
            elif "item" in resp and isinstance(resp["item"], list):
                videos = resp["item"]
            else:
                videos = list(resp.values()) if resp else []
        elif isinstance(resp, list):
            videos = resp

        result = []
        for item in videos:
            if not isinstance(item, dict):
                continue
            pubdate_raw = item.get("created") or item.get("pubdate") or item.get("pub_date")
            pubdate = None
            if pubdate_raw is not None:
                try:
                    pubdate = datetime.fromtimestamp(int(pubdate_raw), tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pubdate = None

            aid = item.get("aid", "")
            result.append({
                "bvid": item.get("bvid", ""),
                "aid": str(aid) if aid is not None else "",
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "pic": item.get("pic", ""),
                "pubdate": pubdate,
            })
        return result
    except Exception as e:
        print(f"[fetch_up_videos] 获取UP主视频列表失败 uid={uid}: {e}")
        return []


async def fetch_video_subtitle(bvid: str) -> str:
    """获取B站视频字幕内容"""
    try:
        v = video.Video(bvid=bvid)
        subtitle_info = await v.get_subtitle()

        if not isinstance(subtitle_info, dict):
            return ""

        subtitles = subtitle_info.get("subtitle", {})
        if isinstance(subtitles, dict):
            sub_list = subtitles.get("subtitles", [])
        elif isinstance(subtitles, list):
            sub_list = subtitles
        else:
            return ""

        if not sub_list:
            return ""

        # 取第一个字幕
        subtitle_url = sub_list[0].get("subtitle_url", "")
        if not subtitle_url:
            return ""

        # 处理URL前缀，确保完整
        if subtitle_url.startswith("//"):
            subtitle_url = "https:" + subtitle_url
        elif subtitle_url.startswith("/"):
            subtitle_url = "https:" + subtitle_url

        async with aiohttp.ClientSession() as session:
            async with session.get(subtitle_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                data = await resp.json()

        body = data.get("body", [])
        if not isinstance(body, list):
            return ""

        contents = []
        for entry in body:
            if isinstance(entry, dict):
                content = entry.get("content", "")
                if content:
                    contents.append(content)

        return "\n".join(contents)
    except Exception as e:
        print(f"[fetch_video_subtitle] 获取视频字幕失败 bvid={bvid}: {e}")
        return ""


async def fetch_favorite_folders(uid: str) -> list[dict]:
    """获取用户创建的收藏夹列表（公开访问，无需Cookie）"""
    try:
        uid_int = int(uid)
    except ValueError:
        print(f"[fetch_favorite_folders] 无效UID: {uid}")
        return []

    try:
        from bilibili_api import favorite_list
        resp = await favorite_list.get_video_favorite_list(uid=uid_int)
        if not resp or not isinstance(resp, dict):
            return []

        folder_list = resp.get("list", []) or []
        result = []
        for item in folder_list:
            if not isinstance(item, dict):
                continue
            result.append({
                "media_id": item.get("id", 0),
                "fid": item.get("fid", 0),
                "title": item.get("title", ""),
                "media_count": item.get("media_count", 0),
            })
        return result
    except Exception as e:
        print(f"[fetch_favorite_folders] 获取收藏夹列表失败 uid={uid}: {e}")
        return []


async def fetch_favorite_videos(media_id: int, pn: int = 1, ps: int = 20) -> tuple[list[dict], bool]:
    """获取收藏夹内容（公开访问，无需Cookie），返回(视频列表, 是否还有更多)"""
    try:
        from bilibili_api import favorite_list
        resp = await favorite_list.get_video_favorite_list_content(media_id=media_id, page=pn)
        if not resp or not isinstance(resp, dict):
            return [], False

        info = resp.get("info", {}) or {}
        total = info.get("media_count", 0)
        has_more = (pn * ps) < total if total else False
        medias = resp.get("medias", []) or []

        result = []
        for item in medias:
            if not isinstance(item, dict):
                continue

            upper = item.get("upper", {}) or {}
            fav_time_raw = item.get("fav_time")
            pubtime_raw = item.get("pubtime")

            fav_time = None
            if fav_time_raw is not None:
                try:
                    fav_time = datetime.fromtimestamp(int(fav_time_raw), tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass

            pubtime = None
            if pubtime_raw is not None:
                try:
                    pubtime = datetime.fromtimestamp(int(pubtime_raw), tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass

            result.append({
                "bvid": item.get("bvid", ""),
                "title": item.get("title", ""),
                "cover": item.get("cover", ""),
                "intro": item.get("intro", ""),
                "duration": item.get("duration", 0),
                "uploader_name": upper.get("name", ""),
                "uploader_mid": str(upper.get("mid", "")),
                "fav_time": fav_time,
                "pubtime": pubtime,
            })
        return result, has_more
    except Exception as e:
        print(f"[fetch_favorite_videos] 获取收藏夹视频失败 media_id={media_id} pn={pn}: {e}")
        return [], False
