# B站 UP 主视频分析系统

一个基于 FastAPI 和 SQLite 的视频信息、字幕、音频转录与内容分析工具。本仓库不包含账号 Cookie、密钥、原有数据库、收藏记录或下载内容。

## 本机运行

使用 Python 3.12 创建虚拟环境并安装依赖：

```bash
python -m venv .venv
# 激活虚拟环境后：
python -m pip install -r requirements.txt
```

将 `.env.example` 复制为 `.env`，按需要配置 B 站登录信息与语言模型或 Whisper 服务。无需相关功能时可以留空。然后启动：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`。该应用目前没有身份鉴权，包含数据删除与批处理接口，应仅在可信本机环境使用。调用 B 站、语言模型和 Whisper 服务需要网络与相应配置；音频处理还需要 ffmpeg。

也可以在准备 `.env` 后运行 `docker compose up --build`。容器端口默认只映射到宿主机回环地址。

## 测试

```bash
python -m pytest -q
```

测试不等于对外部 B 站服务、凭据或转录质量的验收。

## 许可证

本仓库尚未指定许可证。
