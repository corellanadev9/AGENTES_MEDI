import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pypdf import PdfReader
from pypdf.errors import DependencyError

try:
    from .matching import SearchRecord, TextCandidateIndex
except ImportError:
    from matching import SearchRecord, TextCandidateIndex


DEFAULT_PDF_PATH = Path(__file__).resolve().parent / "MEDICAL-FEES-DATA.pdf"
FIRST_CPT_PDF_PAGE = 49
LAST_CPT_PDF_PAGE = 690

CODE_LINE = re.compile(
    r"^\s*(?P<code>\d{4}[0-9A-Z])(?![-\d])(?:\s+)(?P<rest>.+?)\s*$",
    re.IGNORECASE,
)
MODIFIER_LINE = re.compile(r"^\s*\d{4}[0-9A-Z]-(?:26|TC)\b", re.IGNORECASE)
FEES_ONLY = re.compile(r"^\s*(?:\d+(?:\.\d+)?\s+){4}\d+(?:\.\d+)?\s*$")
TRAILING_FEES = re.compile(
    r"^(?P<description>.*?)(?:\s+)(?:\d+(?:\.\d+)?\s+){4}\d+(?:\.\d+)?\s*$"
)
SKIPPED_PREFIXES = (
    "CPT copyright",
    "MEDICAL FEES DIRECTORY",
    "UCR ",
    "MFS ",
    "RVU",
)


def clean_description(parts: list[str]) -> str:
    description = re.sub(r"\s+", " ", " ".join(parts)).strip(" ;")
    return description


def parse_medical_fees_page(text: str, page_number: int) -> list[SearchRecord]:
    records: list[SearchRecord] = []
    pending_code: Optional[str] = None
    pending_parts: list[str] = []

    def finish_pending() -> None:
        nonlocal pending_code, pending_parts
        description = clean_description(pending_parts)
        if pending_code and len(description) >= 4 and re.search(r"[A-Za-z]", description):
            records.append(
                SearchRecord(
                    codigo=pending_code,
                    nombre=description,
                    fuente="medical_fees",
                    pagina_medical_fees=page_number,
                )
            )
        pending_code = None
        pending_parts = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if MODIFIER_LINE.match(line):
            finish_pending()
            continue

        code_match = CODE_LINE.match(line)
        if code_match:
            finish_pending()
            code = code_match.group("code").upper()
            rest = code_match.group("rest")
            fee_match = TRAILING_FEES.match(rest)
            if fee_match:
                description = clean_description([fee_match.group("description")])
                if len(description) >= 4 and re.search(r"[A-Za-z]", description):
                    records.append(
                        SearchRecord(
                            codigo=code,
                            nombre=description,
                            fuente="medical_fees",
                            pagina_medical_fees=page_number,
                        )
                    )
            else:
                pending_code = code
                pending_parts = [rest]
            continue

        if pending_code:
            if FEES_ONLY.match(line):
                finish_pending()
                continue
            if line.startswith(SKIPPED_PREFIXES) or re.fullmatch(r"\d+", line):
                continue
            pending_parts.append(line)

    finish_pending()
    return records


def resolve_pdf_path() -> Path:
    configured_path = os.getenv("MEDICAL_FEES_PDF_PATH")
    return Path(configured_path) if configured_path else DEFAULT_PDF_PATH


@lru_cache(maxsize=2)
def load_medical_fees_records(pdf_path_value: Optional[str] = None) -> tuple[SearchRecord, ...]:
    pdf_path = Path(pdf_path_value) if pdf_path_value else resolve_pdf_path()
    if not pdf_path.exists():
        raise FileNotFoundError(f"No se encontro el PDF Medical Fees en {pdf_path}.")

    try:
        reader = PdfReader(str(pdf_path))
    except DependencyError as exc:
        raise RuntimeError(
            "El PDF Medical Fees usa cifrado AES. Instala las dependencias con "
            "\"python -m pip install 'pypdf[crypto]>=6.0.0'\"."
        ) from exc
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise RuntimeError("No se pudo abrir el PDF Medical Fees protegido.")

    records_by_code: dict[str, SearchRecord] = {}
    last_page = min(LAST_CPT_PDF_PAGE, len(reader.pages))
    for page_number in range(FIRST_CPT_PDF_PAGE, last_page + 1):
        text = reader.pages[page_number - 1].extract_text() or ""
        for record in parse_medical_fees_page(text, page_number):
            records_by_code.setdefault(record.codigo, record)

    if not records_by_code:
        raise RuntimeError("No se pudieron indexar codigos CPT desde Medical Fees.")
    return tuple(records_by_code.values())


@lru_cache(maxsize=2)
def load_medical_fees_index(pdf_path_value: Optional[str] = None) -> TextCandidateIndex:
    return TextCandidateIndex(load_medical_fees_records(pdf_path_value))
