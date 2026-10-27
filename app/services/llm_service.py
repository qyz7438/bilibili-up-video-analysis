import aiohttp
import json
from app.config import settings

DEFAULT_RESULT = {
    "summary": "解析失败",
    "key_points": [],
    "sentiment": "中性",
    "topics": []
}

EMPTY_RESULT = {
    "summary": "输入文本为空或太短，无法分析",
    "key_points": [],
    "sentiment": "中性",
    "topics": []
}


def build_analysis_prompt(text: str) -> str:
    """构建发送给LLM的Prompt字符串"""
    if not text or len(text.strip()) < 10:
        return json.dumps(EMPTY_RESULT, ensure_ascii=False)

    prompt = f"""你是一位专业的视频内容分析师。请对以下B站视频字幕进行结构化分析。

要求：
1. 用3-5句话总结视频核心内容
2. 提取3-5个关键要点
3. 判断整体情感倾向（只能是"正面"/"中性"/"负面"之一）
4. 提取3-5个主题标签

请严格按以下JSON格式输出，不要包含任何其他内容：
{{
  "summary": "3-5句话总结",
  "key_points": ["要点1", "要点2", "要点3"],
  "sentiment": "正面/中性/负面",
  "topics": ["主题1", "主题2", "主题3"]
}}

待分析字幕：
{text}
"""
    return prompt


def parse_analysis_response(content: str) -> dict:
    """解析LLM返回的字符串"""
    try:
        cleaned = content.strip()
        # 去除markdown代码块标记
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        result = json.loads(cleaned)
        if not isinstance(result, dict):
            print("[LLM] 解析结果不是字典，返回兜底")
            return DEFAULT_RESULT.copy()

        # 确保必要字段存在
        for key in ["summary", "key_points", "sentiment", "topics"]:
            if key not in result:
                result[key] = DEFAULT_RESULT[key]
        return result
    except Exception as e:
        print(f"[LLM] 解析响应失败: {e}")
        return DEFAULT_RESULT.copy()


async def analyze_content(text: str) -> dict:
    """使用LLM分析字幕文本内容"""
    # 截断处理，最多8000个字符
    if text:
        text = text[:8000]

    prompt = build_analysis_prompt(text)

    # 如果prompt是JSON（空或太短时的兜底情况），直接解析返回
    if prompt.startswith("{"):
        try:
            return json.loads(prompt)
        except Exception:
            return EMPTY_RESULT.copy()

    print("[LLM] 调用LLM分析...")

    url = f"{settings.LLM_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }

    # 尝试添加 response_format，部分API不支持则忽略
    try:
        payload["response_format"] = {"type": "json_object"}
    except Exception:
        pass

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    resp_text = await response.text()
                    print(f"[LLM] API请求失败，状态码: {response.status}, 响应: {resp_text[:200]}")
                    return DEFAULT_RESULT.copy()

                data = await response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    print("[LLM] API返回内容为空")
                    return DEFAULT_RESULT.copy()

                print("[LLM] 分析完成，解析响应...")
                result = parse_analysis_response(content)
                summary_preview = result.get("summary", "")[:50]
                print(f"[LLM] 分析结果摘要: {summary_preview}...")
                return result

    except aiohttp.ClientError as e:
        print(f"[LLM] 网络请求异常: {e}")
        return DEFAULT_RESULT.copy()
    except Exception as e:
        print(f"[LLM] 分析过程异常: {e}")
        return DEFAULT_RESULT.copy()
