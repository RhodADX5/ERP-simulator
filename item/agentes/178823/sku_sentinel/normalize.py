"""Normalización de texto y atributos técnicos.

Convierte capturas libres como "Memoria Kingston Fury 16 GB DDR5" y
"RAM DDR5 16GB Kingston Fury" a la misma representación, para que el CSP y
el detector de duplicados comparen valores y no ortografía.
"""

from __future__ import annotations

import re
import unicodedata

SYNONYMS = {
    "memoria": "ram", "dimm": "ram",
    "procesador": "cpu",
    "disco": "ssd", "unidad": "ssd",
    "fuente": "psu",
    "grafica": "gpu", "video": "gpu",
    "madre": "motherboard", "placa": "motherboard", "mb": "motherboard",
}
STOPWORDS = {"de", "la", "el", "los", "las", "para", "con", "y", "en", "tarjeta", "m.2", "m2"}

_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(gb|tb|mb|kg|g|w|m)\b", re.IGNORECASE)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def join_units(text: str) -> str:
    """'16 gb' -> '16GB', '750 w' -> '750W'."""
    return _UNIT_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def tokens(text: str) -> set[str]:
    """Bolsa de palabras normalizada para similitud de texto."""
    clean = join_units(strip_accents(text or "")).lower()
    words = re.findall(r"[a-z0-9.]+", clean)
    out = set()
    for w in words:
        w = SYNONYMS.get(w, w)
        if w and w not in STOPWORDS:
            out.add(w)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def normalize_value(value, allowed: list[str] | None = None) -> str:
    """Normaliza un valor de atributo; si hay lista cerrada, devuelve su forma canónica."""
    text = re.sub(r"\s+", " ", join_units(str(value).strip()))
    if allowed:
        for canon in allowed:
            if canon.casefold() == text.casefold():
                return canon
    return text


def normalize_attributes(attrs: dict, domains: dict[str, dict]) -> dict[str, str]:
    """Llaves en minúsculas y valores normalizados según el dominio de la categoría."""
    out = {}
    for key, value in (attrs or {}).items():
        if value is None or str(value).strip() == "":
            continue
        k = strip_accents(str(key)).strip().lower().replace(" ", "_")
        dom = domains.get(k, {})
        out[k] = normalize_value(value, dom.get("allowed"))
    return out


# Extracción de atributos desde texto libre (se usa solo para los que faltan)
_EXTRACTORS = [
    ("tipo", re.compile(r"\b(DDR[345])\b", re.I), lambda m: m.group(1).upper()),
    ("interfaz", re.compile(r"\b(NVMe|SATA)\b", re.I), lambda m: "NVMe" if m.group(1).lower() == "nvme" else "SATA"),
    ("potencia", re.compile(r"\b(\d{3,4})\s*W\b", re.I), lambda m: m.group(1) + "W"),
    ("socket", re.compile(r"\b(AM[45]|LGA\s?1700)\b", re.I), lambda m: m.group(1).upper().replace(" ", "")),
    ("chipset", re.compile(r"\b([ABXZH]\d{3}[A-Z]?)\b"), lambda m: m.group(1)),
    ("capacidad", re.compile(r"\b(\d+)\s*(GB|TB)\b", re.I), lambda m: m.group(1) + m.group(2).upper()),
]


def extract_attributes(text: str) -> dict[str, str]:
    found = {}
    for attr, rx, fmt in _EXTRACTORS:
        m = rx.search(text or "")
        if m:
            found[attr] = fmt(m)
    return found
