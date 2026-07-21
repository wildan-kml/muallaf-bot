from functools import lru_cache

from .config import get_settings
from .rag_pipeline import RagPipeline


@lru_cache(maxsize=1)
def get_chatbot_pipeline() -> RagPipeline:
    settings = get_settings()
    if settings.rag_engine in {"manual", "custom", "legacy", "legacy_manual"}:
        return RagPipeline(settings)

    from .langchain_pipeline import LangChainRagPipeline

    return LangChainRagPipeline(settings)
