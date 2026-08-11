import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional


PHRASE_ALIASES = {
    "RAYOS X": "RADIOLOGIC EXAMINATION",
    "RAYO X": "RADIOLOGIC EXAMINATION",
    "RX": "RADIOLOGIC EXAMINATION",
    "MAXILAR INFERIOR": "RADIOLOGIC EXAMINATION MANDIBLE",
    "MANDIBULA": "RADIOLOGIC EXAMINATION MANDIBLE",
    "MAXILAR SUPERIOR": "RADIOLOGIC EXAMINATION MAXILLA",
    "MASTOIDES": "RADIOLOGIC EXAMINATION MASTOIDS",
    "OIDOS": "RADIOLOGIC EXAMINATION EAR INTERNAL AUDITORY MEATI",
    "OIDO": "RADIOLOGIC EXAMINATION EAR INTERNAL AUDITORY MEATI",
    "ARCO CIGOMATICO": "RADIOLOGIC EXAMINATION FACIAL BONES ZYGOMATIC ARCH",
    "ARCOS CIGOMATICOS": "RADIOLOGIC EXAMINATION FACIAL BONES ZYGOMATIC ARCH",
    "ORBITAS": "RADIOLOGIC EXAMINATION ORBITS",
    "ORBITA": "RADIOLOGIC EXAMINATION ORBITS",
    "HUESOS DE LA NARIZ": "RADIOLOGIC EXAMINATION NASAL BONES",
    "HUESOS NARIZ": "RADIOLOGIC EXAMINATION NASAL BONES",
    "SENOS PARANASALES": "RADIOLOGIC EXAMINATION PARANASAL SINUSES",
    "PROYECCIONES": "VIEWS",
    "PROYECCION": "VIEW",
    "VISTAS": "VIEWS",
    "VISTA": "VIEW",
    "USG": "ULTRASOUND",
    "US": "ULTRASOUND",
    "ULTRASONOGRAFIA": "ULTRASOUND",
    "ULTRASONIDOS": "ULTRASOUND",
    "ULTRASONIDO": "ULTRASOUND",
    "ECOGRAFIA": "ULTRASOUND",
    "TAC": "COMPUTED TOMOGRAPHY",
    "TC": "COMPUTED TOMOGRAPHY",
    "TOMOGRAFIA": "COMPUTED TOMOGRAPHY",
    "RMN": "MAGNETIC RESONANCE",
    "RM": "MAGNETIC RESONANCE",
    "IRM": "MAGNETIC RESONANCE",
    "RESONANCIAS": "MAGNETIC RESONANCE",
    "RESONANCIA MAGNETICA": "MAGNETIC RESONANCE",
    "ECG": "ELECTROCARDIOGRAM",
    "EKG": "ELECTROCARDIOGRAM",
    "EEG": "ELECTROENCEPHALOGRAM",
    "ELECTROCARDIOGRAMA": "ELECTROCARDIOGRAM",
    "CORTISOL TOTAL": "CORTISOL TOTAL",
}

STOP_WORDS = {
    "A",
    "AN",
    "AND",
    "CON",
    "DE",
    "DEL",
    "EL",
    "EN",
    "EXAM",
    "EXAMEN",
    "EXAMINATION",
    "LA",
    "LAS",
    "LOS",
    "O",
    "OF",
    "OR",
    "PARA",
    "POR",
    "PROCEDURE",
    "PROCEDIMIENTO",
    "THE",
    "Y",
}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(character for character in normalized if not unicodedata.combining(character))


def normalize_text(value: Any) -> str:
    text = strip_accents(str(value or "")).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for phrase, replacement in PHRASE_ALIASES.items():
        text = re.sub(rf"\b{re.escape(phrase)}\b", replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def searchable_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) > 1 and token not in STOP_WORDS
    }


@dataclass(frozen=True)
class SearchRecord:
    codigo: str
    nombre: str
    fuente: str
    id_cpt_product: Optional[int | str] = None
    tipo_procedimiento: Optional[str] = None
    pagina_medical_fees: Optional[int] = None
    categoria: Optional[str] = None


class TextCandidateIndex:
    def __init__(self, records: Iterable[SearchRecord]):
        self.records = list(records)
        self.normalized_names = [normalize_text(record.nombre) for record in self.records]
        self.tokens = [
            searchable_tokens(
                " ".join(
                    value
                    for value in (
                        record.nombre,
                        record.tipo_procedimiento,
                        record.categoria,
                    )
                    if value
                )
            )
            for record in self.records
        ]
        self.token_index: dict[str, set[int]] = {}
        self.code_index: dict[str, int] = {}

        for index, record in enumerate(self.records):
            self.code_index.setdefault(normalize_text(record.codigo), index)
            for token in self.tokens[index]:
                self.token_index.setdefault(token, set()).add(index)

    def search(self, code: Any, name: Any, limit: int = 5) -> list[dict[str, Any]]:
        query_code = normalize_text(code)
        query_name = normalize_text(name)
        query_tokens = searchable_tokens(name)

        if query_code in self.code_index:
            candidate_indexes = {self.code_index[query_code]}
        else:
            candidate_indexes: set[int] = set()
            for token in query_tokens:
                candidate_indexes.update(self.token_index.get(token, set()))

        if not candidate_indexes:
            candidate_indexes = set(range(len(self.records)))

        ranked: list[tuple[float, int]] = []
        for index in candidate_indexes:
            record = self.records[index]
            record_tokens = self.tokens[index]
            shared_tokens = query_tokens & record_tokens
            query_coverage = len(shared_tokens) / max(len(query_tokens), 1)
            record_coverage = len(shared_tokens) / max(len(record_tokens), 1)
            sequence_score = SequenceMatcher(
                None, query_name, self.normalized_names[index]
            ).ratio()

            score = (sequence_score * 0.45) + (query_coverage * 0.40) + (record_coverage * 0.15)
            if "RADIOLOGIC" in query_tokens:
                if "RADIOLOGIC" in record_tokens:
                    score += 0.20
                else:
                    score -= 0.10
            if query_code and query_code == normalize_text(record.codigo):
                score = 1.0
            ranked.append((max(0.0, min(score, 1.0)), index))

        ranked.sort(key=lambda item: (-item[0], self.records[item[1]].codigo))
        results: list[dict[str, Any]] = []
        for score, index in ranked[:limit]:
            record = self.records[index]
            results.append(
                {
                    "fuente": record.fuente,
                    "idCptProduct": record.id_cpt_product,
                    "codigo": record.codigo,
                    "nombre": record.nombre,
                    "tipoProcedimiento": record.tipo_procedimiento,
                    "paginaMedicalFees": record.pagina_medical_fees,
                    "categoria": record.categoria,
                    "scorePreliminar": round(score * 100),
                }
            )
        return results
