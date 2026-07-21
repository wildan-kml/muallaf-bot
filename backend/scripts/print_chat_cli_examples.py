"""Cetak contoh output CLI chatbot untuk dokumentasi skripsi.

Script ini dapat dipakai untuk membuat screenshot terminal pada Bab IV.
Jika backend FastAPI sedang berjalan, script akan mencoba mengambil respons
aktual dari endpoint /api/chat. Jika backend tidak aktif, script tetap
menampilkan contoh fallback statis agar format dokumentasi tetap tersedia.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from typing import Any
from urllib import error, request


DEFAULT_API_URL = "http://127.0.0.1:8000/api/chat"

EXAMPLES = {
    "answer": {
        "title": "Gambar 4.6 Contoh Jawaban Chatbot Berdasarkan Konteks Dokumen",
        "question": "Saya baru belajar Islam, sebenarnya inti ajaran Islam itu apa?",
        "fallback": {
            "answer": (
                "Jika baru tertarik mengenal Islam, mulailah dari hal paling dasar: mengenal Allah, "
                "memahami makna syahadat, dan mempelajari rukun iman serta rukun Islam secara bertahap. "
                "Setelah itu, pelajari ibadah harian yang paling pokok seperti bersuci, wudhu, dan shalat. "
                "Kamu tidak harus memahami semuanya sekaligus; proses belajar mualaf memang perlu "
                "pendampingan, latihan, dan pembinaan yang berkelanjutan."
            ),
            "mode": "rag_guided",
            "escalation": None,
            "retrieval_confidence": 0.7309,
            "sources": [
                {"document_title": "Mengenal Islam Lebih Dekat bersama Masjid Agung Sunda Kelapa", "page_number": 26},
                {"document_title": "Kurikulum & Modul Pembinaan Mualaf", "page_number": 23},
                {"document_title": "Mengenal Islam Lebih Dekat bersama Masjid Agung Sunda Kelapa", "page_number": 21},
                {"document_title": "Mengenal Islam Lebih Dekat bersama Masjid Agung Sunda Kelapa", "page_number": 66},
            ],
        },
    },
    "fallback": {
        "title": "Gambar 4.7 Contoh Respons Fallback pada Pertanyaan Sensitif",
        "question": (
            "Saya baru masuk Islam, tetapi keluarga saya menolak dan saya merasa tertekan. "
            "Saya harus bagaimana?"
        ),
        "fallback": {
            "answer": (
                "Pertanyaan ini berkaitan dengan kondisi pribadi yang sensitif dan sebaiknya "
                "dibicarakan langsung dengan pembina IMC-MASK. Pembina dapat mendengarkan "
                "kondisi kamu secara lebih utuh dan membantu memberi arahan yang lebih aman, "
                "bijak, dan sesuai dengan keadaan keluarga kamu.\n\n"
                "Saran:\n"
                "Silakan hubungi pembina atau sekretariat IMC-MASK untuk pendampingan lanjutan."
            ),
            "mode": "fallback",
            "escalation": "mentor",
            "retrieval_confidence": None,
            "sources": [],
        },
    },
    "out_of_scope": {
        "title": "Contoh Respons Fallback pada Pertanyaan di Luar Konteks",
        "question": "Siapa Presiden Indonesia saat ini?",
        "fallback": {
            "answer": (
                "Pertanyaan ini berada di luar cakupan Muallaf Bot. Saat ini saya difokuskan "
                "untuk menjawab topik dasar tentang mualaf, syahadat, pembinaan, ibadah, "
                "akhlak, dan layanan IMC-MASK."
            ),
            "mode": "fallback",
            "escalation": "out_of_scope_question",
            "retrieval_confidence": 0,
            "sources": [],
        },
    },
}


def post_chat(api_url: str, question: str, timeout: int = 45) -> dict[str, Any]:
    payload = json.dumps({"question": question}).encode("utf-8")
    req = request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wrap_text(text: str, width: int = 76) -> str:
    paragraphs = [item.strip() for item in str(text or "").split("\n\n")]
    wrapped = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        lines = paragraph.splitlines()
        wrapped.append("\n".join(textwrap.fill(line.strip(), width=width) for line in lines if line.strip()))
    return "\n\n".join(wrapped)


def format_page(page: Any) -> str:
    if page in (None, "", 0):
        return ""
    return f", halaman {page}"


def print_example(case: str, api_url: str, use_live: bool) -> None:
    example = EXAMPLES[case]
    response = example["fallback"]
    source_note = ""

    if use_live:
        try:
            response = post_chat(api_url=api_url, question=example["question"])
            source_note = "Respons diambil dari backend aktif."
        except (error.URLError, TimeoutError, OSError) as exc:
            source_note = f"Backend tidak aktif atau tidak merespons ({exc}). Menampilkan contoh statis."

    title = example["title"]
    print("=" * len(title))
    print(title)
    print("=" * len(title))
    print()
    print("[REQUEST]")
    print(f"Endpoint : POST {api_url}")
    print(f"Question : {example['question']}")
    print()
    print("[RESPONSE]")
    print(f"Mode                  : {response.get('mode') or '-'}")
    print(f"Escalation            : {response.get('escalation') or '-'}")

    confidence = response.get("retrieval_confidence")
    confidence_label = "-" if confidence is None else f"{float(confidence):.4f}"
    print(f"Retrieval Confidence  : {confidence_label}")

    sources = response.get("sources") or []
    print(f"Jumlah Rujukan        : {len(sources)}")
    print()
    print("Jawaban:")
    print(wrap_text(response.get("answer") or response.get("reply") or ""))
    print()
    print("Rujukan:")
    if sources:
        for index, source in enumerate(sources, start=1):
            title = source.get("document_title") or source.get("source") or "Dokumen"
            print(f"{index}. {title}{format_page(source.get('page_number'))}")
    else:
        print("Tidak ditampilkan karena respons ini merupakan fallback atau tidak memiliki rujukan dokumen.")
    print()
    print("[CATATAN]")
    print(source_note or "Contoh statis untuk dokumentasi.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cetak contoh CLI Muallaf Bot untuk skripsi.")
    parser.add_argument("--case", choices=sorted(EXAMPLES), default="answer")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--static", action="store_true", help="Jangan panggil backend; tampilkan contoh statis.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print_example(case=args.case, api_url=args.api_url, use_live=not args.static)


if __name__ == "__main__":
    main()
