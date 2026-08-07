from dataclasses import asdict, dataclass
from pathlib import Path
import re


DOCUMENT_TITLE_ALIASES = {
    "BUKU MILD EDISI KEDUA": "Mengenal Islam Lebih Dekat bersama Masjid Agung Sunda Kelapa",
    "MENGENAL ISLAM LEBIH DEKAT BERSAMA MASJID AGUNG SUNDA KELAPA": "Mengenal Islam Lebih Dekat bersama Masjid Agung Sunda Kelapa",
    "MODUL PEMBINAAN MUALAF": "Modul Pembinaan Mualaf",
    "HANDBOOK TATACARA IBADAH PRAKTIS MCB": "Tata Cara Ibadah Praktis untuk Mualaf",
    "TATACARA IBADAH PRAKTIS UNTUK MUALAF MCB": "Tata Cara Ibadah Praktis untuk Mualaf",
    "TATA CARA IBADAH PRAKTIS UNTUK MUALAF BAZNAS": "Tata Cara Ibadah Praktis untuk Mualaf",
    "TATA CARA IBADAH PRAKTIS UNTUK MUALAF": "Tata Cara Ibadah Praktis untuk Mualaf",
    "FIQIH MUALAF BAZNAS": "Fiqih Mualaf",
    "FIQIH MUALAF": "Fiqih Mualaf",
}


CANONICAL_DOCUMENT_FILES = {
    "Mengenal Islam Lebih Dekat bersama Masjid Agung Sunda Kelapa": "Mengenal Islam Lebih Dekat bersama Masjid Agung Sunda Kelapa.pdf",
    "Modul Pembinaan Mualaf": "Modul Pembinaan Mualaf.pdf",
    "Tata Cara Ibadah Praktis untuk Mualaf": "Tata Cara Ibadah Praktis untuk Mualaf.pdf",
    "Fiqih Mualaf": "Fiqih Mualaf.pdf",
}


def _title_key(value: str) -> str:
    base = Path(str(value or "")).stem
    base = base.replace("_", " ")
    key = re.sub(r"\s+", " ", base).strip().upper()
    if "MODUL PEMBINAAN MUALAF" in key:
        return "MODUL PEMBINAAN MUALAF"
    return key


def normalize_document_title(file_name: str = "", document_title: str = "") -> str:
    for candidate in (document_title, file_name):
        key = _title_key(candidate)
        if key in DOCUMENT_TITLE_ALIASES:
            return DOCUMENT_TITLE_ALIASES[key]
    return str(document_title or Path(str(file_name)).stem or "Dokumen Rujukan")


def normalize_document_file_name(file_name: str = "", document_title: str = "") -> str:
    current = str(file_name or "")
    if current == "imc-mask-website" or not current:
        return current
    title = normalize_document_title(file_name=current, document_title=document_title)
    return CANONICAL_DOCUMENT_FILES.get(title, current)


ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")


def _contains_arabic(text: str) -> bool:
    return bool(ARABIC_CHAR_RE.search(str(text or "")))


def _arabic_ratio(text: str) -> float:
    value = str(text or "")
    if not value.strip():
        return 0.0
    return len(ARABIC_CHAR_RE.findall(value)) / max(len(value.strip()), 1)


def _compact_arabic_spaces(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return re.sub(r"(?<=[\u0600-\u06FF])\s+(?=[\u0600-\u06FF])", "", value)


def _repair_fragmented_arabic_blocks(text: str) -> str:
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    repaired: list[str] = []
    arabic_block: list[str] = []

    def flush_arabic_block() -> None:
        nonlocal arabic_block
        if not arabic_block:
            return
        meaningful = [line.strip() for line in arabic_block if line.strip()]
        if meaningful:
            reversed_lines = list(reversed(meaningful))
            merged = "".join(_compact_arabic_spaces(line) for line in reversed_lines)
            repaired.append(_compact_arabic_spaces(merged))
        arabic_block = []

    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            flush_arabic_block()
            repaired.append("")
            continue

        if _contains_arabic(line) and (_arabic_ratio(line) >= 0.22 or len(line) <= 24):
            arabic_block.append(line)
            continue

        flush_arabic_block()
        repaired.append(line)

    flush_arabic_block()
    return "\n".join(repaired)


@dataclass
class PageText:
    file_name: str
    document_title: str
    page_number: int
    text: str


@dataclass
class TextChunk:
    chunk_id: str
    content: str
    document_title: str
    page_number: int
    file_name: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TextChunk":
        raw_file_name = str(data.get("file_name", ""))
        document_title = normalize_document_title(
            file_name=raw_file_name,
            document_title=str(data.get("document_title", "")),
        )
        file_name = normalize_document_file_name(
            file_name=raw_file_name,
            document_title=document_title,
        )
        return cls(
            chunk_id=str(data.get("chunk_id", "")),
            content=str(data.get("content", "")),
            document_title=document_title,
            page_number=int(data.get("page_number") or 0),
            file_name=file_name,
        )


def build_imc_mask_website_chunks() -> list["TextChunk"]:
    document_title = "Website International Muallaf Center Masjid Agung Sunda Kelapa (IMC-MASK)"
    file_name = "imc-mask-website"
    chunks = [
        TextChunk(
            chunk_id="imc_mask_website_syahadat_flow_c1",
            document_title=document_title,
            file_name=file_name,
            page_number=1,
            content=(
                "Alur ikrar syahadat di IMC-MASK adalah sebagai berikut: "
                "1. Isi formulir dan surat pernyataan. "
                "2. Lengkapi dokumen persyaratan. "
                "3. Serahkan berkas paling lambat H-1. "
                "4. Hadir 1 jam sebelum prosesi. "
                "5. Membawa 2 saksi laki-laki muslim dewasa. "
                "6. Mengikuti pembinaan minimal 4 pertemuan. "
                "7. Sertifikat diberikan setelah pembinaan selesai."
            ),
        ),
        TextChunk(
            chunk_id="imc_mask_website_syahadat_requirements_c2",
            document_title=document_title,
            file_name=file_name,
            page_number=1,
            content=(
                "Persyaratan dokumen ikrar syahadat di IMC-MASK meliputi formulir pernyataan, "
                "materai Rp10.000, fotokopi KTP untuk WNI, fotokopi paspor untuk WNA, "
                "fotokopi KK khusus anak-anak, pas foto 3x4 sebanyak 2 lembar, dan pas foto 4x6 sebanyak 2 lembar. "
                "Catatan: pas foto wanita memakai hijab atau kerudung, dan laki-laki memakai peci atau kopiah."
            ),
        ),
        TextChunk(
            chunk_id="imc_mask_website_syahadat_schedule_c3",
            document_title=document_title,
            file_name=file_name,
            page_number=1,
            content=(
                "Informasi kelas pembinaan IMC-MASK: jadwal kelas setiap hari Rabu dan Sabtu, "
                "pukul 10.00 sampai 16.00 WIB, bertempat di Gedung Fatahillah Lt. 4, Masjid Agung Sunda Kelapa. "
                "Materi pembinaan meliputi Studi Islam Dasar, Fiqih Ibadah, Akhlak Karimah, dan Pengenalan Al-Qur'an."
            ),
        ),
    ]
    return chunks


def clean_document_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("\x00", " ")
    text = _repair_fragmented_arabic_blocks(text)
    text = re.sub(r"\.{5,}", ". ", text)
    text = re.sub(r"_{4,}|-{4,}", " ", text)
    text = re.sub(r"^\s*[ivxlcdm]{1,8}\b\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\d+\s*//\s*BAZNAS\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\d{1,4}\s+(?=[A-ZÀ-Þ])", "", text)
    text = re.sub(r"\b([A-Za-zÀ-ÿ]+)-\s+([A-Za-zÀ-ÿ]+)\b", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_non_content_page(page: PageText) -> bool:
    text = clean_document_text(page.text)
    lowered = text.lower()
    title = page.document_title.lower()

    if not text or len(text) < 80:
        return True

    front_matter_markers = {
        "kata pengantar",
        "daftar isi",
        "sambutan ketua",
        "sambutan direktur",
        "biografi penulis",
        "daftar pustaka",
        "daftar kehadiran",
        "latihan soal",
    }
    closing_markers = {
        "bab vi penutup",
        "penutup",
        "kesimpulan",
        "saran dan rekomendasi",
    }

    if any(marker in lowered for marker in front_matter_markers):
        return True
    if any(marker in lowered[:260] for marker in closing_markers):
        return True
    if re.search(r"\bdaftar\s+isi\b", lowered):
        return True
    if re.search(r"\.{3,}\s*\d+", page.text):
        return True

    if "mengenal islam lebih dekat" in title and page.page_number < 20:
        return True
    if "mengenal islam lebih dekat" in title and page.page_number >= 183:
        return True
    if "modul pembinaan mualaf" in title and page.page_number < 8:
        return True
    if "modul pembinaan mualaf" in title and page.page_number >= 218:
        return True

    return False


def _split_long_sentence(sentence: str, chunk_size: int) -> list[str]:
    if len(sentence) <= chunk_size:
        return [sentence]

    parts = re.split(r"(?<=[,;:])\s+", sentence)
    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip()
        if current and len(candidate) > chunk_size:
            chunks.append(current)
            current = part
        else:
            current = candidate

    if current:
        chunks.append(current)

    normalized: list[str] = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            normalized.append(chunk)
            continue
        words = chunk.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > chunk_size:
                normalized.append(current)
                current = word
            else:
                current = candidate
        if current:
            normalized.append(current)
    return normalized


def _sentence_spans(cleaned: str, chunk_size: int) -> list[tuple[str, int]]:
    spans: list[tuple[str, int]] = []
    pattern = re.compile(r".+?(?:[.!?](?=\s+[A-Z0-9À-Þ])|$)")
    for match in pattern.finditer(cleaned):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        offset_delta = match.group(0).find(sentence)
        start = match.start() + max(offset_delta, 0)
        cursor = start
        for piece in _split_long_sentence(sentence, chunk_size):
            piece = piece.strip()
            if not piece:
                continue
            piece_start = cleaned.find(piece[: min(len(piece), 32)], cursor)
            if piece_start == -1:
                piece_start = cursor
            spans.append((piece, piece_start))
            cursor = piece_start + len(piece)
    return spans


def chunk_text_spans(text: str, chunk_size: int, overlap: int) -> list[tuple[str, int]]:
    cleaned = clean_document_text(text)
    if not cleaned:
        return []

    chunk_size = max(250, chunk_size)
    sentences = _sentence_spans(cleaned, chunk_size)

    chunks: list[tuple[str, int]] = []
    current_sentences: list[tuple[str, int]] = []
    current_length = 0

    for sentence, start in sentences:
        sentence_length = len(sentence)
        projected = current_length + sentence_length + (1 if current_sentences else 0)
        if current_sentences and projected > chunk_size:
            chunk = " ".join(item for item, _ in current_sentences).strip()
            chunks.append((chunk, current_sentences[0][1]))
            current_sentences = (
                current_sentences[-1:]
                if overlap > 0 and len(current_sentences[-1][0]) < chunk_size * 0.4
                else []
            )
            current_length = sum(len(item) for item, _ in current_sentences) + max(0, len(current_sentences) - 1)
        current_sentences.append((sentence, start))
        current_length += sentence_length + (1 if current_length else 0)

    if current_sentences:
        chunk = " ".join(item for item, _ in current_sentences).strip()
        chunks.append((chunk, current_sentences[0][1]))

    return [(chunk, start) for chunk, start in chunks if len(chunk) >= 80]


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    return [chunk for chunk, _ in chunk_text_spans(text, chunk_size=chunk_size, overlap=overlap)]


def _page_for_offset(page_offsets: list[tuple[int, int]], offset: int) -> int:
    current_page = page_offsets[0][1] if page_offsets else 0
    for page_offset, page_number in page_offsets:
        if page_offset > offset:
            break
        current_page = page_number
    return current_page


def chunk_pages(pages: list[PageText], chunk_size: int, overlap: int) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    grouped_pages: dict[str, list[PageText]] = {}
    for page in pages:
        grouped_pages.setdefault(page.file_name, []).append(page)

    for file_name, document_pages in grouped_pages.items():
        filtered_pages = [page for page in sorted(document_pages, key=lambda item: item.page_number) if not is_non_content_page(page)]
        if not filtered_pages:
            continue

        document_text_parts: list[str] = []
        page_offsets: list[tuple[int, int]] = []
        cursor = 0
        for page in filtered_pages:
            cleaned_page_text = clean_document_text(page.text)
            if not cleaned_page_text:
                continue
            page_offsets.append((cursor, page.page_number))
            document_text_parts.append(cleaned_page_text)
            cursor += len(cleaned_page_text) + 1

        document_text = " ".join(document_text_parts)
        if not document_text:
            continue

        document_title = filtered_pages[0].document_title
        safe_title = re.sub(r"[^a-zA-Z0-9]+", "_", document_title).strip("_").lower()
        for index, (content, start_offset) in enumerate(chunk_text_spans(document_text, chunk_size=chunk_size, overlap=overlap), start=1):
            if content[:1].islower():
                continue
            page_number = _page_for_offset(page_offsets, start_offset)
            chunks.append(
                TextChunk(
                    chunk_id=f"{safe_title}_p{page_number}_c{index}",
                    content=content,
                    document_title=document_title,
                    page_number=page_number,
                    file_name=file_name,
                )
            )
    return chunks
