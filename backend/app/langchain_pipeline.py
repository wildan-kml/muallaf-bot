import logging
from typing import Any

from .config import Settings
from .rag_pipeline import (
    RagPipeline,
    _claims_context_is_insufficient,
    _format_chat_history,
    _make_prompt,
    _without_unverified_arabic,
)
from .schemas import ChatMessage
from .preprocessing import TextChunk
from .vector_store import RetrievalResult
from .vector_store import LangChainVectorStoreRetriever


logger = logging.getLogger(__name__)


def _response_text(response: Any) -> str | None:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip() or None

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, dict):
                text = block.get("text")
            else:
                text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        combined = "\n".join(parts).strip()
        return combined or None

    return str(content).strip() or None


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
                metadata = document.metadata
                chunk = chunks_by_id.get(metadata.get("chunk_id"))
                if chunk is None:
                    # A remote pgvector result remains usable even when the
                    # container has no generated local chunk file.
                    chunk = TextChunk(
                        chunk_id=str(metadata.get("chunk_id") or "remote-chunk"),
                        content=document.page_content,
                        document_title=str(metadata.get("document_title") or "Dokumen rujukan"),
                        page_number=int(metadata.get("page_number") or 1),
                        file_name=str(metadata.get("file_name") or ""),
                    )
                results.append(
                    RetrievalResult(
                        chunk=chunk,
                        score=float(document.metadata.get("score", 0.0)),
                    )
                )
            return results
        except Exception:
            logger.warning("LangChain retriever failed; falling back to base retriever.", exc_info=True)
            return super()._retrieve_results(query, top_k)

    def _generate_answer(
        self,
        question: str,
        results: list[RetrievalResult],
        history: list[ChatMessage] | None = None,
    ) -> str | None:
        for provider in self._generation_providers():
            generated = self._try_generate_with_provider(provider, question, results, history=history)
            if generated and _claims_context_is_insufficient(generated):
                logger.warning(
                    "LangChain %s returned an over-conservative context refusal; trying the next provider.",
                    provider,
                )
                continue
            if generated:
                return generated
        return None

    def _try_generate_with_provider(
        self,
        provider: str,
        question: str,
        results: list[RetrievalResult],
        history: list[ChatMessage] | None = None,
    ) -> str | None:
        try:
            return self._generate_answer_with_provider(provider, question, results, history=history)
        except Exception:
            logger.warning(
                "LangChain %s generation failed; trying next fallback path if available.",
                provider,
                exc_info=True,
            )
            return None

    def _generate_answer_with_provider(
        self,
        provider: str,
        question: str,
        results: list[RetrievalResult],
        history: list[ChatMessage] | None = None,
    ) -> str | None:
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
        return _response_text(response)

    def _langchain_ready(self) -> bool:
        try:
            self._prompt_template()
        except Exception:
            logger.debug("LangChain prompt template initialization failed.", exc_info=True)
            return False

        for provider in self._generation_providers():
            if self._langchain_provider_ready(provider):
                return True
        return False

    def _langchain_provider_ready(self, provider: str) -> bool:
        try:
            self._langchain_llm(provider=provider)
            return True
        except Exception:
            logger.debug("LangChain %s readiness check failed.", provider, exc_info=True)
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
Batasi jawaban sekitar 80–180 kata kecuali pengguna meminta penjelasan lebih rinci.
Gunakan bahasa Indonesia sepenuhnya; jangan menyisipkan kata penghubung bahasa Inggris.
Jika pengguna meminta tata cara, urutan, langkah, persiapan, atau beberapa contoh, gunakan daftar bernomor atau berpoin dengan satu gagasan per butir; jangan menulisnya sebagai paragraf panjang.
Pastikan jawaban benar-benar menjawab pertanyaan terbaru. Jika konteks membahas topik lain, jangan gunakan bagian tersebut untuk mengarang jawaban.
Sebelum menjawab, periksa seluruh blok konteks dan gunakan fakta yang secara langsung mendukung pertanyaan, meskipun fakta tersebut tersebar di beberapa blok.
Jangan mengatakan informasi tidak tersedia atau konteks tidak cukup jika setidaknya satu blok secara eksplisit memuat jawaban yang diminta.
Untuk pertanyaan utang-piutang, konteks tentang mengambil harta orang lain dengan niat mengembalikan, amanah, dan menunaikan janji adalah bukti yang langsung relevan; rangkum prinsip tersebut dan jangan menyatakan topiknya tidak dibahas.
Jika konteks hanya mendukung sebagian jawaban, sampaikan bagian yang didukung terlebih dahulu lalu jelaskan secara spesifik bagian apa yang belum tersedia; jangan menolak seluruh pertanyaan.
Pertahankan daftar faktual sebagaimana tertulis dalam konteks. Jangan memindahkan, menambah, mengurangi, atau mengganti anggota rukun, syarat, urutan, nama, angka, dan kategori.
Jika beberapa potongan konteks saling bertentangan atau tidak cukup untuk menyusun daftar lengkap, jelaskan keterbatasannya secara singkat; jangan menebak anggota yang hilang.
Jangan membuat fatwa baru, jangan membahas kasus pribadi sensitif secara final.
Jika konteks tidak cukup, arahkan pengguna untuk menghubungi pembina IMC-MASK.
Jangan menyalin tabel, daftar hadir, daftar isi, atau baris dokumen administratif.
Jangan menambahkan kalimat "jawaban ini bersifat informasi awal" kecuali konteks benar-benar tidak cukup.
Gunakan riwayat percakapan hanya untuk memahami maksud pertanyaan lanjutan.
Jika pertanyaan terbaru hanya berupa lanjutan seperti "ajarkan lebih lengkap", "lanjutkan", "lebih detail", atau "apa yang harus saya siapkan", pahami sebagai kelanjutan dari pertanyaan pengguna terakhir.
Jika pertanyaan terbaru sudah jelas membahas topik baru, abaikan riwayat percakapan.
Jangan menjawab hanya berdasarkan riwayat; konteks dokumen tetap sumber utama.
Jangan menulis kutipan Arab atau mengklaim sebuah terjemahan sebagai pasangan teks Arab. Teks Arab hasil ekstraksi PDF sengaja tidak disertakan karena belum diverifikasi per kutipan.
Jangan menyebut sebuah riwayat sebagai hadis sahih atau menisbahkannya kepada perawi tertentu kecuali status dan pasangan teksnya tertulis jelas dalam konteks.

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
                    f"Isi: {_without_unverified_arabic(chunk.content)}"
                )
            )
        return "\n\n".join(context_blocks)

    def _langchain_llm(self, provider: str | None = None):
        provider = provider or self.settings.llm_provider
        if provider == "groq":
            if not self.settings.groq_api_key:
                raise RuntimeError("GROQ_API_KEY belum tersedia.")
            from langchain_groq import ChatGroq

            return ChatGroq(
                model=self.settings.groq_model,
                api_key=self.settings.groq_api_key,
                temperature=0.2,
                timeout=45,
                max_retries=1,
                max_tokens=700,
                reasoning_effort="low",
                reasoning_format="hidden",
            )

        if provider == "gemini":
            if not self.settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY belum tersedia.")
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=self.settings.gemini_model,
                google_api_key=self.settings.gemini_api_key,
                temperature=0.2,
                timeout=15,
                max_retries=0,
                max_output_tokens=500,
            )

        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=self.settings.ollama_model,
                base_url=self.settings.ollama_base_url,
                temperature=0.2,
                num_ctx=2048,
                num_predict=220,
                client_kwargs={"timeout": 55.0},
                async_client_kwargs={"timeout": 55.0},
            )

        if provider == "auto":
            for configured_provider in self._generation_providers():
                return self._langchain_llm(configured_provider)

        raise RuntimeError(f"LLM provider tidak didukung LangChain: {provider}")


def make_langchain_prompt_preview(question: str, results: list[RetrievalResult]) -> str:
    return _make_prompt(question, results)
