"""应用配置：从环境变量读取。"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings:
    # LLM provider：deepseek（默认，国内直连）| anthropic
    llm_provider: str = os.getenv("LLM_PROVIDER", "deepseek")

    # DeepSeek（OpenAI 兼容接口）
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")  # deepseek-chat | deepseek-reasoner
    deepseek_vision_model: str = os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-v4-flash-vision-exp")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # Anthropic（备选，需代理）
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

    # Embedding provider：bge（本地）| dashscope | openai
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "bge")
    hf_endpoint: str = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    milvus_uri: str = os.getenv("MILVUS_URI", "http://127.0.0.1:19530")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/appliance_doctor"
    )
    data_dir: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR.parent / "data")))


settings = Settings()

# 关键：pymilvus 在 import 时读 MILVUS_URI 环境变量作为默认地址；
# Windows 不支持其内置 ./milvus_lite.db 嵌入式文件模式（会报 Illegal uri），
# 因此显式写入合法 URI，保证 import pymilvus 不炸。
os.environ.setdefault("MILVUS_URI", settings.milvus_uri)
# HuggingFace 走国内镜像，加速/绕过 BGE 模型下载
os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
