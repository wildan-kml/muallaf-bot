from typing import Any

from .config import Settings
from .rag_pipeline import (
    RagPipeline,
    _format_chat_history,
    _make_prompt,
)
from .schemas import ChatMessage
from .vector_store import RetrievalResult
from .vector_store import LangChainVectorStoreRetriever


class LangChainRagPipeline(RagPipeline):
    """Optional LangChain-backed answer generator.

    Retrieval, guardrail, curated answers, source formatting, and website
    metadata intentionally remain in the stable custom pipeline. LangChain is
    used here as an interchangeable LLM orchestration layer so the project can
    compare both approaches without changing the frontend contract.
    """

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.langchain_retriever = LangChainVectorStoreRetriever(
            self.vector_store,
            top_k=max(self.settings.top_k, 8),
        )

    def status(self) -> dict[str, Any]:
        status = super().status()
        status["mode"] = "rag_langchain"
        status["rag_engine"] = "langchain"
        status["langchain_ready"] = self._langchain_ready()
        status["langchain_retriever"] = True
        return status

    def refresh(self) -> None:
        super().refresh()
        self.langchain_retriever = LangChainVectorStoreRetriever(
            self.vector_store,
            top_k=max(self.settings.top_k, 8),
        )

    def _retrieve_results(self, query: str, top_k: int) -> list[RetrievalResult]:
        try:
            self.langchain_retriever = LangChainVectorStoreRetriever(self.vector_store, top_k=top_k)
            documents = self.langchain_retriever.invoke(query)
            chunks_by_id = {chunk.chunk_id: chunk for chunk in self.vector_store.chunks}
            results: list[RetrievalResult] = []
            for document in documents:
                chunk = chunks_by_id.get(document.metadata.get("chunk_id"))
                if chunk is None:
                    continue
                results.append(
                    RetrievalResult(
                        chunk=chunk,
                        score=float(document.metadata.get("score", 0.0)),
                    )
                )
            return results
        except Exception:
            return super()._retrieve_results(query, top_k)

    def _generate_answer(
        self,
        question: str,
        results: list[RetrievalResult],
        history: list[ChatMessage] | None = None,
    ) -> str | None:
        if self.settings.llm_provider == "auto":
            return self._generate_answer_with_provider(
                "gemini",
                question,
                results,
                history=history,
            ) or self._generate_answer_with_provider(
                "ollama",
                question,
                results,
                history=history,
            )
        return self._generate_answer_with_provider(self.settings.llm_provider, question, results, history=history)

    def _generate_answer_with_provider(
        self,
        provider: str,
        question: str,
        results: list[RetrievalResult],
        history: list[ChatMessage] | None = None,
    ) -> str | None:
        try:
            prompt_template = self._prompt_template()
            llm = self._langchain_llm(provider=provider)
            chain = prompt_template | llm
            response = chain.invoke(
                {
                    "question": question,
                    "context": self._format_context(results),
                    "history": _format_chat_history(history),
                }
            )
            text = getattr(response, "content", response)
            return str(text).strip() or None
        except Exception:
            return None

    def _langchain_ready(self) -> bool:
        try:
            self._prompt_template()
            self._langchain_llm(provider=self.settings.llm_provider)
            return True
        except Exception:
            return False

    def _prompt_template(self):
        from langchain_core.prompts import PromptTemplate

        # Keep the wording aligned with the existing custom prompt.
        return PromptTemplate.from_template(
            """
Anda adalah Muallaf Bot IMC-MASK untuk edukasi dasar mualaf.
Jawab hanya berdasarkan konteks dokumen di bawah.
Gunakan bahasa Indonesia yang lembut, ringkas, dan mudah dipahami.
Jawab langsung, tanpa awalan "Berdasarkan dokumen rujukan yang tersedia".
Jangan membuat fatwa baru, jangan membahas kasus pribadi sensitif secara final.
Jika konteks tidak cukup, arahkan pengguna untuk menghubungi pembina IMC-MASK.
Jangan menyalin tabel, daftar hadir, daftar isi, atau baris dokumen administratif.
Jangan menambahkan kalimat "jawaban ini bersifat informasi awal" kecuali konteks benar-benar tidak cukup.
Gunakan riwayat percakapan hanya untuk memahami maksud pertanyaan lanjutan.
Jika pertanyaan terbaru hanya berupa lanjutan seperti "ajarkan lebih lengkap", "lanjutkan", atau "lebih detail", pahami sebagai kelanjutan dari pertanyaan pengguna terakhir.
Jika pertanyaan terbaru sudah jelas membahas topik baru, abaikan riwayat percakapan.
Jangan menjawab hanya berdasarkan riwayat; konteks dokumen tetap sumber utama.

Riwayat percakapan:
{history}

Konteks dokumen:
{context}

Pertanyaan pengguna:
{question}

Jawaban:
""".strip()
        )

    def _format_context(self, results: list[RetrievalResult]) -> str:
        context_blocks = []
        for index, result in enumerate(results, start=1):
            chunk = result.chunk
            context_blocks.append(
                (
                    f"[{index}] Dokumen: {chunk.document_title}\n"
                    f"Halaman: {chunk.page_number}\n"
                    f"Isi: {chunk.content}"
                )
            )
        return "\n\n".join(context_blocks)

    def _langchain_llm(self, provider: str | None = None):
        provider = provider or self.settings.llm_provider
        if provider == "gemini":
            if not self.settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY belum tersedia.")
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=self.settings.gemini_model,
                google_api_key=self.settings.gemini_api_key,
                temperature=0.2,
            )

        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=self.settings.ollama_model,
                base_url=self.settings.ollama_base_url,
                temperature=0.2,
            )

        if provider == "auto":
            try:
                if self.settings.gemini_api_key:
                    from langchain_google_genai import ChatGoogleGenerativeAI

                    return ChatGoogleGenerativeAI(
                        model=self.settings.gemini_model,
                        google_api_key=self.settings.gemini_api_key,
                        temperature=0.2,
                    )
            except Exception:
                pass

            if self.settings.ollama_base_url and self.settings.ollama_model:
                from langchain_ollama import ChatOllama

                return ChatOllama(
                    model=self.settings.ollama_model,
                    base_url=self.settings.ollama_base_url,
                    temperature=0.2,
                )

        raise RuntimeError(f"LLM provider tidak didukung LangChain: {provider}")


def make_langchain_prompt_preview(question: str, results: list[RetrievalResult]) -> str:
    return _make_prompt(question, results)
