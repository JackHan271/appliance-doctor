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
    # gRPC keepalive 间隔（毫秒）。Milvus 会对过于频繁的 ping 返回
    # GOAWAY(ENHANCE_YOUR_CALM/too_many_pings) 并断连，调长可避免。
    # 0 = 用 pymilvus 默认值。
    milvus_keepalive_ms: int = int(os.getenv("MILVUS_KEEPALIVE_MS", "60000"))
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/appliance_doctor"
    )
    data_dir: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR.parent / "data")))

    # ---- 模型路由（成本控制）----
    # 强模型用于诊断/审查/核验；轻模型用于摘要/分类等高频轻任务
    deepseek_model_strong: str = os.getenv("DEEPSEEK_MODEL_STRONG", "")
    deepseek_model_light: str = os.getenv("DEEPSEEK_MODEL_LIGHT", "")

    # ---- 缓存 ----
    cache_enabled: bool = os.getenv("CACHE_ENABLED", "1") not in ("0", "false", "False")
    cache_ttl: int = int(os.getenv("CACHE_TTL", "3600"))
    cache_maxsize: int = int(os.getenv("CACHE_MAXSIZE", "512"))
    redis_url: str = os.getenv("REDIS_URL", "")

    # ---- RAG 检索链路 ----
    # rag_mode: hybrid（稠密+BM25+RRF）| dense（纯向量）
    rag_mode: str = os.getenv("RAG_MODE", "hybrid")
    # 第一阶段粗召回条数（两路各召回这么多，再融合）
    rag_recall_n: int = int(os.getenv("RAG_RECALL_N", "20"))
    # 重排：用 Cross-Encoder 对融合后的候选精排
    rerank_enabled: bool = os.getenv("RERANK_ENABLED", "1") not in ("0", "false", "False")
    rerank_model: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-base")
    rerank_max_length: int = int(os.getenv("RERANK_MAX_LENGTH", "512"))
    # 送入重排的候选数上限（重排是 O(n) 次推理，要控住）
    rerank_candidates: int = int(os.getenv("RERANK_CANDIDATES", "20"))

    # ---- 上下文工程 / 记忆 ----
    # 上下文总预算（估算 token）：超过则把早期历史折叠成摘要
    context_budget_tokens: int = int(os.getenv("CONTEXT_BUDGET_TOKENS", "3000"))
    # 折叠时保留最近几轮原文
    history_keep_turns: int = int(os.getenv("HISTORY_KEEP_TURNS", "3"))
    # 滚动摘要的字符上限（防止摘要自己无限膨胀）
    summary_max_chars: int = int(os.getenv("SUMMARY_MAX_CHARS", "600"))

    @property
    def rag_quota(self) -> dict:
        """每个知识库**保底**进入重排器的候选数。

        只有权重还不够：实测权重 1.5 时，融合后前 20 名全是故障码，
        手册一条都进不了重排器——那"冰箱有异味怎么办"这类
        **没有故障码的查询**就会失衡。配额保证两类知识都能被重排器看到，
        最终由 Cross-Encoder 按真实相关性裁决。
        """
        raw = os.getenv("RAG_QUOTA", "")
        if raw:
            try:
                import json as _json

                return _json.loads(raw)
            except ValueError:
                pass
        return {"fault_code": 12, "manual": 8}

    @property
    def rag_weights(self) -> dict:
        """分库检索权重（加权 RRF）。故障码是结构化高置信知识，权重高于手册，
        避免被数量更多的手册片段淹没。可用 RAG_WEIGHTS 环境变量覆盖（JSON）。"""
        raw = os.getenv("RAG_WEIGHTS", "")
        if raw:
            try:
                import json as _json

                return _json.loads(raw)
            except ValueError:
                pass
        return {"fault_code": 1.5, "manual": 1.0}

    @property
    def model_prices(self) -> dict:
        """模型价格表（每 100 万 token 单价，元）。可用 MODEL_PRICES 环境变量覆盖（JSON）。"""
        raw = os.getenv("MODEL_PRICES", "")
        if raw:
            try:
                import json as _json

                return _json.loads(raw)
            except ValueError:
                pass
        return {}


settings = Settings()

# 关键：pymilvus 在 import 时读 MILVUS_URI 环境变量作为默认地址；
# Windows 不支持其内置 ./milvus_lite.db 嵌入式文件模式（会报 Illegal uri），
# 因此显式写入合法 URI，保证 import pymilvus 不炸。
os.environ.setdefault("MILVUS_URI", settings.milvus_uri)
# HuggingFace 走国内镜像，加速/绕过 BGE 模型下载
os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
