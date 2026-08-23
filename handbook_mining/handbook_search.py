"""Local ASM Metals Handbook mining tool.

This script performs a text-only scan of the local handbook PDF, builds a
page-level discovery index, extracts compact candidate records, writes
targeted context snippets, and audits the current calculator databases
without modifying them.

The workflow is intentionally conservative:
- native PDF text extraction only
- no OCR
- no curve digitization
- no writes to the production engineering CSV databases
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - fallback for environments using the legacy import name.
    try:
        import fitz  # type: ignore
    except ImportError as exc:  # pragma: no cover
        fitz = None  # type: ignore
        _FITZ_IMPORT_ERROR = exc
    else:
        _FITZ_IMPORT_ERROR = None
else:
    _FITZ_IMPORT_ERROR = None


ROOT_DIR = Path(__file__).resolve().parent
REPO_DIR = ROOT_DIR.parent
DEFAULT_PDF = REPO_DIR / "REFERENCES" / "metals-handbook-desk-edition-2nd-edition_compress.pdf"
OUTPUT_DIR = ROOT_DIR / "output"

STATIC_DB = REPO_DIR / "materials_static.csv"
FATIGUE_DB = REPO_DIR / "materials_fatigue.csv"
WALKER_DB = REPO_DIR / "materials_walker.csv"
MATERIAL_DB = REPO_DIR / "materials.csv"


DEFAULT_MATERIAL_VARIANTS: Dict[str, List[str]] = {
    "Aluminum 2024-T3": [
        "aluminum 2024-t3",
        "2024-t3",
        "2024 t3",
        "aa 2024",
        "2024-t3 aluminum",
    ],
    "Inconel 718": [
        "inconel 718",
        "haynes 718",
        "alloy 718",
        "718 alloy",
    ],
    "Ti-6Al-4V": [
        "ti-6al-4v",
        "ti 6al 4v",
        "ti6al4v",
        "astm grade 5",
        "grade 5 titanium",
    ],
    "Nickel 625": [
        "inconel 625",
        "nickel 625",
        "alloy 625",
        "haynes 625",
        "625 nickel",
    ],
    "316 Stainless Steel": [
        "316 stainless steel",
        "316 stainless",
        "aisi 316",
        "type 316",
        "316h",
        "316h stainless steel",
    ],
    "AISI 4340": [
        "aisi 4340",
        "4340 steel",
        "alloy steel 4340",
        "4340",
    ],
    "Aluminum 7075-T6": [
        "aluminum 7075-t6",
        "7075-t6",
        "7075 t6",
        "aa 7075",
        "7075 aluminum",
    ],
    "Haynes 230": [
        "haynes 230",
        "alloy 230",
    ],
    "Rene 41": [
        "rene 41",
        "rené 41",
        "rene41",
    ],
}


KEYWORD_PATTERNS: List[Tuple[str, Sequence[str]]] = [
    ("fatigue", ["fatigue"]),
    ("fatigue life", ["fatigue life"]),
    ("low-cycle fatigue", ["low-cycle fatigue", "lcf"]),
    ("high-cycle fatigue", ["high-cycle fatigue", "hcf"]),
    ("strain-life", ["strain-life", "strain life"]),
    ("stress-life", ["stress-life", "stress life"]),
    ("s-n curve", ["s-n curve", "sn curve", "s-n"]),
    ("cyclic stress-strain", ["cyclic stress-strain", "cyclic stress strain"]),
    ("ramberg-osgood", ["ramberg-osgood", "ramberg osgood"]),
    ("coffin-manson", ["coffin-manson", "coffin manson"]),
    ("basquin", ["basquin"]),
    ("fatigue strength coefficient", ["fatigue strength coefficient"]),
    ("fatigue ductility coefficient", ["fatigue ductility coefficient"]),
    ("fatigue strength exponent", ["fatigue strength exponent"]),
    ("fatigue ductility exponent", ["fatigue ductility exponent"]),
    ("mean stress", ["mean stress"]),
    ("stress ratio", ["stress ratio"]),
    ("r ratio", ["r ratio", "r-ratio"]),
    ("walker", ["walker"]),
    ("smith-watson-topper", ["smith-watson-topper", "smith watson topper", "swt"]),
    ("morrow", ["morrow"]),
    ("goodman", ["goodman"]),
    ("temperature", ["temperature", "elevated temperature", "temperature-dependent", "temperature dependent"]),
    ("runout", ["runout", "run out"]),
    ("frequency", ["frequency"]),
    ("strain rate", ["strain rate"]),
    ("environment", ["environment"]),
    ("test standard", ["test standard", "astm", "iso 12106", "astm e606"]),
    ("heat treatment", ["heat treatment", "solution treated", "aged", "annealed", "welded", "welding"]),
    ("product form", ["plate", "sheet", "bar", "forged", "casting", "wrought", "wire", "tube"]),
    ("young's modulus", ["young's modulus", "young modulus", "modulus of elasticity"]),
    ("ultimate tensile strength", ["ultimate tensile strength", "uts", "tensile strength"]),
    ("yield strength", ["yield strength"]),
    ("poisson ratio", ["poisson ratio", "poisson's ratio", "nu"]),
    ("thermal conductivity", ["thermal conductivity"]),
    ("specific heat", ["specific heat"]),
    ("density", ["density"]),
    ("cte", ["coefficient of thermal expansion", "thermal expansion", "cte", "thermal expansion coefficient"]),
]


CATEGORY_PRIORITY = [
    "LCF",
    "HCF",
    "MEAN_STRESS",
    "CYCLIC_PROPERTY",
    "STATIC_PROPERTY",
    "TEMPERATURE_DATA",
    "EXPERIMENTAL_DATA",
    "GENERAL_FATIGUE",
    "UNKNOWN",
]


CATEGORY_RULES: List[Tuple[str, Sequence[str]]] = [
    ("LCF", ["low-cycle fatigue", "lcf", "strain-life", "coffin-manson", "basquin", "sigma_f", "epsilon_f"]),
    ("HCF", ["high-cycle fatigue", "hcf", "stress-life", "s-n curve", "s-n", "endurance", "fatigue strength"]),
    ("MEAN_STRESS", ["mean stress", "stress ratio", "r ratio", "r-ratio", "walker", "smith-watson-topper", "swt", "morrow", "goodman"]),
    ("CYCLIC_PROPERTY", ["cyclic stress-strain", "ramberg-osgood", "cyclic", "k'", "n'"]),
    ("STATIC_PROPERTY", ["young's modulus", "ultimate tensile strength", "yield strength", "poisson", "thermal conductivity", "specific heat", "density", "coefficient of thermal expansion", "thermal expansion", "cte"]),
    ("TEMPERATURE_DATA", ["temperature", "elevated temperature", "temperature-dependent", "temperature dependent"]),
    ("EXPERIMENTAL_DATA", ["frequency", "strain rate", "environment", "test standard", "runout", "heat treatment", "product form", "specimen"]),
    ("GENERAL_FATIGUE", ["fatigue", "fatigue life"]),
]


PROPERTY_GROUPS = [
    {
        "category": "STATIC_PROPERTY",
        "property_name": "E",
        "aliases": ["young's modulus", "young modulus", "modulus of elasticity"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["gpa", "mpa", "pa"],
    },
    {
        "category": "STATIC_PROPERTY",
        "property_name": "S_u",
        "aliases": ["ultimate tensile strength", "uts", "tensile strength"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["mpa", "gpa", "pa"],
    },
    {
        "category": "STATIC_PROPERTY",
        "property_name": "S_y",
        "aliases": ["yield strength"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["mpa", "gpa", "pa"],
    },
    {
        "category": "STATIC_PROPERTY",
        "property_name": "nu",
        "aliases": ["poisson ratio", "poisson's ratio"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": [],
    },
    {
        "category": "STATIC_PROPERTY",
        "property_name": "thermal_conductivity",
        "aliases": ["thermal conductivity"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["w/mk"],
    },
    {
        "category": "STATIC_PROPERTY",
        "property_name": "specific_heat",
        "aliases": ["specific heat"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["j/kgk"],
    },
    {
        "category": "STATIC_PROPERTY",
        "property_name": "density",
        "aliases": ["density"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["kg/m3", "g/cm3"],
    },
    {
        "category": "STATIC_PROPERTY",
        "property_name": "CTE",
        "aliases": ["coefficient of thermal expansion", "thermal expansion", "thermal expansion coefficient", "cte"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["1/c", "/c"],
    },
    {
        "category": "CYCLIC_PROPERTY",
        "property_name": "K'",
        "aliases": ["cyclic stress-strain", "ramberg-osgood", "ramberg osgood"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["mpa"],
    },
    {
        "category": "CYCLIC_PROPERTY",
        "property_name": "n'",
        "aliases": ["cyclic stress-strain", "ramberg-osgood", "ramberg osgood"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": [],
    },
    {
        "category": "LCF",
        "property_name": "sigma_f'",
        "aliases": ["sigma_f", "sigma_f'", "fatigue strength coefficient", "basquin"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": ["mpa"],
    },
    {
        "category": "LCF",
        "property_name": "b",
        "aliases": ["basquin", "fatigue strength exponent"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": [],
    },
    {
        "category": "LCF",
        "property_name": "epsilon_f'",
        "aliases": ["epsilon_f", "epsilon_f'", "fatigue ductility coefficient", "coffin-manson"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": [],
    },
    {
        "category": "LCF",
        "property_name": "c",
        "aliases": ["coffin-manson", "fatigue ductility exponent"],
        "origin": "SOURCE_REPORTED",
        "preferred_units": [],
    },
    {
        "category": "HCF",
        "property_name": "S-N data",
        "aliases": ["s-n curve", "stress-life", "high-cycle fatigue", "endurance"],
        "origin": "CURVE_DIGITIZATION_REQUIRED",
        "preferred_units": [],
    },
    {
        "category": "MEAN_STRESS",
        "property_name": "mean-stress data",
        "aliases": ["mean stress", "stress ratio", "r ratio", "walker", "smith-watson-topper", "swt", "morrow", "goodman"],
        "origin": "CURVE_DIGITIZATION_REQUIRED",
        "preferred_units": [],
    },
]


NUMERIC_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
TEMP_RE = re.compile(r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>deg\s*c|c|k|f)\b", re.IGNORECASE)
FREQ_RE = re.compile(r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>hz|khz|mhz)\b", re.IGNORECASE)
STRAIN_RATE_RE = re.compile(r"(?P<value>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*/\s*s\b", re.IGNORECASE)
RATIO_RE = re.compile(r"\b(?:r|r-ratio|stress ratio)\s*[:=]?\s*(?P<value>-?\d+(?:\.\d+)?)", re.IGNORECASE)
CYCLES_RE = re.compile(r"\b(?P<value>\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*(cycles|reversals|rev)\b", re.IGNORECASE)
TABLE_RE = re.compile(r"\btable\s+([a-z0-9.\-]+)", re.IGNORECASE)
FIGURE_RE = re.compile(r"\bfig(?:ure)?\.?\s*([a-z0-9.\-]+)", re.IGNORECASE)


@dataclass
class PageHit:
    pdf_page: int
    printed_page: str
    material: str
    matched_keywords: str
    category: str
    relevance_score: float
    snippet: str
    source_pdf: str
    review_status: str = "UNREVIEWED"
    notes: str = ""


@dataclass
class CandidateRow:
    candidate_id: str
    material: str
    material_condition: str
    product_form: str
    temperature_C: str
    property_or_data_type: str
    property_name: str
    value: str
    units: str
    sigma_max_MPa: str
    sigma_min_MPa: str
    sigma_a_MPa: str
    sigma_m_MPa: str
    R_ratio: str
    strain_amplitude: str
    life_cycles: str
    reversals: str
    runout: str
    frequency_Hz: str
    strain_rate: str
    environment: str
    test_standard: str
    pdf_page: str
    printed_page: str
    table_number: str
    figure_number: str
    source_text: str
    extraction_method: str
    confidence: str
    review_status: str
    engineering_notes: str
    data_origin: str


def slugify(value: str) -> str:
    value = value.strip().replace("/", "_").replace("\\", "_")
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("._-") or "unknown"


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def load_pdf(pdf_path: Path):
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF is not available. Install it with: python -m pip install pymupdf"
        ) from _FITZ_IMPORT_ERROR
    return fitz.open(str(pdf_path))


def pdf_signature(pdf_path: Path) -> Dict[str, object]:
    stat = pdf_path.stat()
    return {
        "path": str(pdf_path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def ensure_output_dirs(base_dir: Path) -> Dict[str, Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "base": base_dir,
        "materials": base_dir / "materials",
        "general": base_dir / "general_fatigue",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def load_cached_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def read_csv_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def collapse_text(text: str) -> str:
    return normalize_ws(text).replace("\u00ad", "")


def find_printed_page(text: str) -> str:
    lines = [normalize_ws(line) for line in text.splitlines() if normalize_ws(line)]
    if not lines:
        return ""
    candidates: List[str] = []
    for line in lines[:4] + lines[-4:]:
        if re.fullmatch(r"[A-Z]?\d{1,4}(?:\.\d+)?", line):
            candidates.append(line)
        match = re.fullmatch(r"(?:page\s*)?([A-Z]?\d{1,4}(?:\.\d+)?)", line, re.IGNORECASE)
        if match:
            candidates.append(match.group(1))
    if candidates:
        return candidates[0]
    for line in lines[:2] + lines[-2:]:
        match = re.search(r"\b([A-Z]?\d{1,4}(?:\.\d+)?)\b", line)
        if match and len(line) <= 12:
            return match.group(1)
    return ""


def detect_table_figure(text: str) -> Tuple[str, str]:
    table = ""
    figure = ""
    table_match = TABLE_RE.search(text)
    if table_match:
        table = f"Table {table_match.group(1)}"
    figure_match = FIGURE_RE.search(text)
    if figure_match:
        figure = f"Figure {figure_match.group(1)}"
    return table, figure


def detect_metadata(text: str) -> dict:
    temperature = ""
    match = TEMP_RE.search(text)
    if match:
        value = match.group("value")
        unit = match.group("unit").lower().replace("deg ", "")
        unit = "C" if unit == "c" else unit.upper()
        temperature = f"{value} {unit}"

    frequency = ""
    match = FREQ_RE.search(text)
    if match:
        frequency = f"{match.group('value')} {match.group('unit').upper()}"

    strain_rate = ""
    match = STRAIN_RATE_RE.search(text)
    if match:
        strain_rate = f"{match.group('value')} /s"

    ratio = ""
    match = RATIO_RE.search(text)
    if match:
        ratio = match.group("value")

    cycles = ""
    match = CYCLES_RE.search(text)
    if match:
        cycles = match.group("value")

    env = ""
    env_terms = ["air", "vacuum", "salt", "water", "oxidizing", "inert", "argon", "helium", "corrosion"]
    for term in env_terms:
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            env = term
            break

    condition_terms = [
        "annealed",
        "aged",
        "solution treated",
        "solutionized",
        "welded",
        "welding",
        "forged",
        "cast",
        "sheet",
        "plate",
        "bar",
        "wire",
        "tube",
        "wrought",
        "heat treated",
        "hot rolled",
        "cold rolled",
        "machined",
        "polished",
    ]
    material_condition = ""
    for term in condition_terms:
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            material_condition = term
            break

    test_standard = ""
    for term in ["ASTM", "ISO 12106", "ASTM E606", "ASTM E466"]:
        if term.lower() in text.lower():
            test_standard = term
            break

    return {
        "temperature": temperature,
        "frequency": frequency,
        "strain_rate": strain_rate,
        "R": ratio,
        "cycles": cycles,
        "environment": env,
        "material_condition": material_condition,
        "test_standard": test_standard,
    }


def term_hits(text_lower: str, variants: Sequence[str]) -> List[str]:
    hits = []
    for variant in variants:
        if variant.lower() in text_lower:
            hits.append(variant)
    return hits


def classify_category(matched_keywords: Sequence[str]) -> str:
    joined = " ".join(matched_keywords).lower()
    for category, patterns in CATEGORY_RULES:
        for pattern in patterns:
            if pattern in joined:
                return category
    return "UNKNOWN"


def infer_category_from_text(text_lower: str) -> str:
    for category, patterns in CATEGORY_RULES:
        for pattern in patterns:
            if pattern in text_lower:
                return category
    return "UNKNOWN"


def relevance_score(material_hits: Sequence[str], keywords: Sequence[str], category: str, text: str) -> float:
    score = 0.0
    if material_hits:
        score += 50.0
        score += min(10.0, 2.0 * len(material_hits))
    if keywords:
        score += min(25.0, 4.0 * len(set(keywords)))
    category_bonus = {
        "LCF": 20.0,
        "HCF": 20.0,
        "MEAN_STRESS": 18.0,
        "CYCLIC_PROPERTY": 15.0,
        "STATIC_PROPERTY": 12.0,
        "TEMPERATURE_DATA": 8.0,
        "EXPERIMENTAL_DATA": 8.0,
        "GENERAL_FATIGUE": 6.0,
        "UNKNOWN": 0.0,
    }
    score += category_bonus.get(category, 0.0)
    if "table" in text.lower() or "figure" in text.lower():
        score += 5.0
    if len(NUMERIC_RE.findall(text)) >= 5:
        score += 5.0
    return min(score, 100.0)


def snippet_for_terms(text: str, terms: Sequence[str], window: int = 220) -> str:
    if not text:
        return ""
    lowered = text.lower()
    positions = []
    for term in terms:
        idx = lowered.find(term.lower())
        if idx >= 0:
            positions.append((idx, term))
    if positions:
        idx, term = min(positions, key=lambda item: item[0])
    else:
        idx = 0
        term = ""
    start = max(0, idx - window)
    end = min(len(text), idx + window)
    snippet = collapse_text(text[start:end])
    if not snippet and term:
        snippet = term
    return snippet[:420]


def extract_numeric_value(window: str, preferred_units: Sequence[str]) -> Tuple[str, str]:
    if not window:
        return "", ""
    lowered = window.lower()
    preferred_units_lower = [unit.lower() for unit in preferred_units]
    candidates = []
    for match in NUMERIC_RE.finditer(window):
        value = match.group(0)
        tail = lowered[match.end() : match.end() + 24]
        units = ""
        for unit in preferred_units_lower:
            if tail.strip().startswith(unit):
                units = unit
                break
        if not units:
            unit_match = re.match(r"\s*([A-Za-z/%°\-\^0-9]+)", tail)
            if unit_match:
                token = unit_match.group(1).strip()
                if token:
                    units = token
        candidates.append((value, units))
    if candidates:
        return candidates[0]
    return "", ""


def extract_temperature(window: str) -> str:
    match = TEMP_RE.search(window)
    if not match:
        return ""
    unit = match.group("unit").lower().replace("deg ", "")
    if unit == "c":
        unit = "C"
    else:
        unit = unit.upper()
    return f"{match.group('value')} {unit}"


def extract_ratio(window: str) -> str:
    match = RATIO_RE.search(window)
    return match.group("value") if match else ""


def extract_cycles(window: str) -> str:
    match = CYCLES_RE.search(window)
    return match.group("value") if match else ""


def extract_frequency(window: str) -> str:
    match = FREQ_RE.search(window)
    if not match:
        return ""
    return f"{match.group('value')} {match.group('unit').upper()}"


def extract_strain_rate(window: str) -> str:
    match = STRAIN_RATE_RE.search(window)
    return f"{match.group('value')} /s" if match else ""


def locate_conditions(text: str) -> Tuple[str, str]:
    material_condition = ""
    product_form = ""
    condition_terms = [
        "annealed",
        "aged",
        "solution treated",
        "solutionized",
        "welded",
        "welding joint",
        "forged",
        "cast",
        "wrought",
        "hot rolled",
        "cold rolled",
    ]
    product_terms = [
        "plate",
        "sheet",
        "bar",
        "wire",
        "tube",
        "forging",
        "casting",
    ]
    for term in condition_terms:
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            material_condition = term
            break
    for term in product_terms:
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            product_form = term
            break
    return material_condition, product_form


def find_table_figure(text: str) -> Tuple[str, str]:
    table, figure = detect_table_figure(text)
    return table, figure


def build_candidate_from_group(
    pdf_page: int,
    printed_page: str,
    material: str,
    text: str,
    group: dict,
    category: str,
    table_number: str,
    figure_number: str,
    extra: dict,
) -> Optional[CandidateRow]:
    lowered = text.lower()
    matches = [alias for alias in group["aliases"] if alias in lowered]
    if not matches:
        return None
    matched_terms = matches or list(group["aliases"][:1])
    snippet = snippet_for_terms(text, matched_terms)
    window = snippet
    value = ""
    units = ""
    if group["origin"] == "SOURCE_REPORTED":
        value, units = extract_numeric_value(window, group.get("preferred_units", []))
    extraction_method = "native_text_extraction"
    data_origin = group["origin"]
    confidence = "0.72" if data_origin == "SOURCE_REPORTED" else "0.55"
    if not value and group["origin"] == "SOURCE_REPORTED":
        extraction_method = "source_text_only"
        confidence = "0.60"
    if group["origin"] == "CURVE_DIGITIZATION_REQUIRED":
        extraction_method = "figure_or_curve_reference"
        confidence = "0.50"
    temperature = extra.get("temperature", "")
    material_condition = extra.get("material_condition", "")
    product_form = extra.get("product_form", "")
    frequency = extra.get("frequency", "")
    strain_rate = extra.get("strain_rate", "")
    env = extra.get("environment", "")
    test_standard = extra.get("test_standard", "")
    ratio = extra.get("R", "")
    cycles = extra.get("cycles", "")
    runout = "Yes" if "runout" in lowered or "run out" in lowered else ""
    sigma_max = extra.get("sigma_max", "")
    sigma_min = extra.get("sigma_min", "")
    sigma_a = extra.get("sigma_a", "")
    sigma_m = extra.get("sigma_m", "")
    strain_amp = extra.get("strain_amplitude", "")
    notes = "Handbook text hit; verify condition, units, and table/figure context before use."
    return CandidateRow(
        candidate_id=f"p{pdf_page:04d}_{slugify(material or 'general')}_{slugify(group['property_name'])}",
        material=material,
        material_condition=material_condition,
        product_form=product_form,
        temperature_C=temperature,
        property_or_data_type=group["category"],
        property_name=group["property_name"],
        value=value,
        units=units,
        sigma_max_MPa=sigma_max,
        sigma_min_MPa=sigma_min,
        sigma_a_MPa=sigma_a,
        sigma_m_MPa=sigma_m,
        R_ratio=ratio,
        strain_amplitude=strain_amp,
        life_cycles=cycles,
        reversals="",
        runout=runout,
        frequency_Hz=frequency,
        strain_rate=strain_rate,
        environment=env,
        test_standard=test_standard,
        pdf_page=str(pdf_page),
        printed_page=printed_page,
        table_number=table_number,
        figure_number=figure_number,
        source_text=snippet,
        extraction_method=extraction_method,
        confidence=confidence,
        review_status="UNREVIEWED",
        engineering_notes=notes,
        data_origin=data_origin,
    )


def detect_explicit_sigma_values(text: str) -> dict:
    result = {"sigma_max": "", "sigma_min": "", "sigma_a": "", "sigma_m": "", "strain_amplitude": ""}
    patterns = {
        "sigma_max": [rf"sigma\s*max\s*[:=]?\s*({NUMERIC_RE.pattern})\s*([A-Za-z/%\-\^0-9]*)"],
        "sigma_min": [rf"sigma\s*min\s*[:=]?\s*({NUMERIC_RE.pattern})\s*([A-Za-z/%\-\^0-9]*)"],
        "sigma_a": [
            rf"sigma\s*a\s*[:=]?\s*({NUMERIC_RE.pattern})\s*([A-Za-z/%\-\^0-9]*)",
            rf"stress amplitude\s*[:=]?\s*({NUMERIC_RE.pattern})\s*([A-Za-z/%\-\^0-9]*)",
        ],
        "sigma_m": [
            rf"sigma\s*m\s*[:=]?\s*({NUMERIC_RE.pattern})\s*([A-Za-z/%\-\^0-9]*)",
            rf"mean stress\s*[:=]?\s*({NUMERIC_RE.pattern})\s*([A-Za-z/%\-\^0-9]*)",
        ],
        "strain_amplitude": [
            rf"strain amplitude\s*[:=]?\s*({NUMERIC_RE.pattern})\s*([A-Za-z/%\-\^0-9]*)",
            rf"epsilon\s*a\s*[:=]?\s*({NUMERIC_RE.pattern})\s*([A-Za-z/%\-\^0-9]*)",
        ],
    }
    for key, regexes in patterns.items():
        for regex in regexes:
            match = re.search(regex, text, re.IGNORECASE)
            if match:
                result[key] = match.group(1)
                break
    return result


def collect_page_hits(
    doc,
    source_pdf: Path,
    progress_every: int,
) -> Tuple[List[PageHit], List[CandidateRow], dict]:
    page_hits: List[PageHit] = []
    candidates: List[CandidateRow] = []
    stats = {
        "pages_scanned": 0,
        "pages_with_hits": 0,
        "material_hits": {},
        "category_hits": {},
    }
    source_pdf_str = str(source_pdf.resolve())

    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        text = collapse_text(page.get_text("text"))
        text_lower = text.lower()
        if not text:
            stats["pages_scanned"] += 1
            continue

        material_hits = []
        for canonical, variants in DEFAULT_MATERIAL_VARIANTS.items():
            hits = term_hits(text_lower, variants)
            if hits:
                material_hits.append((canonical, hits))
                stats["material_hits"][canonical] = stats["material_hits"].get(canonical, 0) + 1

        matched_keywords = []
        for canonical, variants in KEYWORD_PATTERNS:
            hits = term_hits(text_lower, variants)
            if hits:
                matched_keywords.append(canonical)

        category = classify_category(matched_keywords)
        if category == "UNKNOWN":
            category = infer_category_from_text(text_lower)

        has_relevant_text = bool(material_hits or matched_keywords)
        if not has_relevant_text:
            stats["pages_scanned"] += 1
            if progress_every and (page_index + 1) % progress_every == 0:
                print(f"Scanned {page_index + 1}/{doc.page_count} pages; relevant pages so far: {stats['pages_with_hits']}")
            continue

        printed_page = find_printed_page(text)
        table_number, figure_number = detect_table_figure(text)
        extra = detect_metadata(text)
        extra.update(detect_explicit_sigma_values(text))
        score = relevance_score(
            [item for _, hits in material_hits for item in hits],
            matched_keywords,
            category,
            text,
        )
        snippet_terms = []
        if material_hits:
            snippet_terms.extend([material_hits[0][0]])
            snippet_terms.extend(material_hits[0][1])
        snippet_terms.extend(matched_keywords)
        snippet = snippet_for_terms(text, snippet_terms)
        if not snippet:
            snippet = text[:420]

        if material_hits:
            for canonical, hits in material_hits:
                row_category = category
                if row_category == "UNKNOWN" and hits:
                    row_category = infer_category_from_text(text_lower)
                hit = PageHit(
                    pdf_page=page_index + 1,
                    printed_page=printed_page,
                    material=canonical,
                    matched_keywords=";".join(sorted(set(matched_keywords))),
                    category=row_category,
                    relevance_score=round(score, 2),
                    snippet=snippet[:420],
                    source_pdf=source_pdf_str,
                    review_status="UNREVIEWED",
                    notes="Native text search hit.",
                )
                page_hits.append(hit)
                stats["pages_with_hits"] += 1
                stats["category_hits"][row_category] = stats["category_hits"].get(row_category, 0) + 1

                page_candidate_count = 0
                if row_category in {"STATIC_PROPERTY", "CYCLIC_PROPERTY", "LCF", "HCF", "MEAN_STRESS"}:
                    for group in PROPERTY_GROUPS:
                        if group["category"] == row_category:
                            candidate = build_candidate_from_group(
                                page_index + 1,
                                printed_page,
                                canonical,
                                text,
                                group,
                                row_category,
                                table_number,
                                figure_number,
                                extra,
                            )
                            if candidate:
                                candidates.append(candidate)
                                page_candidate_count += 1
                    if page_candidate_count == 0:
                        candidates.append(
                            CandidateRow(
                                candidate_id=f"p{page_index + 1:04d}_{slugify(canonical)}_{slugify(row_category)}_reference",
                                material=canonical,
                                material_condition=extra.get("material_condition", ""),
                                product_form=extra.get("product_form", ""),
                                temperature_C=extra.get("temperature", ""),
                                property_or_data_type=row_category,
                                property_name=f"{row_category.lower()} reference",
                                value="",
                                units="",
                                sigma_max_MPa=extra.get("sigma_max", ""),
                                sigma_min_MPa=extra.get("sigma_min", ""),
                                sigma_a_MPa=extra.get("sigma_a", ""),
                                sigma_m_MPa=extra.get("sigma_m", ""),
                                R_ratio=extra.get("R", ""),
                                strain_amplitude=extra.get("strain_amplitude", ""),
                                life_cycles=extra.get("cycles", ""),
                                reversals="",
                                runout="Yes" if "runout" in text_lower else "",
                                frequency_Hz=extra.get("frequency", ""),
                                strain_rate=extra.get("strain_rate", ""),
                                environment=extra.get("environment", ""),
                                test_standard=extra.get("test_standard", ""),
                                pdf_page=str(page_index + 1),
                                printed_page=printed_page,
                                table_number=table_number,
                                figure_number=figure_number,
                                source_text=snippet[:420],
                                extraction_method="category_reference",
                                confidence="0.44",
                                review_status="UNREVIEWED",
                                engineering_notes="Category-level material hit; inspect the page for explicit property labels or tables.",
                                data_origin="UNKNOWN",
                            )
                        )
                else:
                    if row_category == "GENERAL_FATIGUE":
                        candidate = build_candidate_from_group(
                            page_index + 1,
                            printed_page,
                            canonical,
                            text,
                            {
                                "category": "GENERAL_FATIGUE",
                                "property_name": "general fatigue reference",
                                "aliases": ["fatigue"],
                                "origin": "UNKNOWN",
                                "preferred_units": [],
                            },
                            row_category,
                            table_number,
                            figure_number,
                            extra,
                        )
                        if candidate:
                            candidates.append(candidate)

        elif matched_keywords:
            hit = PageHit(
                pdf_page=page_index + 1,
                printed_page=printed_page,
                material="",
                matched_keywords=";".join(sorted(set(matched_keywords))),
                category=category,
                relevance_score=round(score, 2),
                snippet=snippet[:420],
                source_pdf=source_pdf_str,
                review_status="UNREVIEWED",
                notes="General fatigue or property hit without explicit material match.",
            )
            page_hits.append(hit)
            stats["pages_with_hits"] += 1
            stats["category_hits"][category] = stats["category_hits"].get(category, 0) + 1

            if category in {"LCF", "HCF", "MEAN_STRESS", "CYCLIC_PROPERTY", "STATIC_PROPERTY"}:
                page_candidate_count = 0
                for group in PROPERTY_GROUPS:
                    if group["category"] == category:
                        candidate = build_candidate_from_group(
                            page_index + 1,
                            printed_page,
                            "",
                            text,
                            group,
                            category,
                            table_number,
                            figure_number,
                            extra,
                        )
                        if candidate:
                            candidates.append(candidate)
                            page_candidate_count += 1
                if page_candidate_count == 0:
                    candidates.append(
                        CandidateRow(
                            candidate_id=f"p{page_index + 1:04d}_general_{slugify(category)}_reference",
                            material="",
                            material_condition=extra.get("material_condition", ""),
                            product_form=extra.get("product_form", ""),
                            temperature_C=extra.get("temperature", ""),
                            property_or_data_type=category,
                            property_name=f"{category.lower()} reference",
                            value="",
                            units="",
                            sigma_max_MPa=extra.get("sigma_max", ""),
                            sigma_min_MPa=extra.get("sigma_min", ""),
                            sigma_a_MPa=extra.get("sigma_a", ""),
                            sigma_m_MPa=extra.get("sigma_m", ""),
                            R_ratio=extra.get("R", ""),
                            strain_amplitude=extra.get("strain_amplitude", ""),
                            life_cycles=extra.get("cycles", ""),
                            reversals="",
                            runout="Yes" if "runout" in text_lower else "",
                            frequency_Hz=extra.get("frequency", ""),
                            strain_rate=extra.get("strain_rate", ""),
                            environment=extra.get("environment", ""),
                            test_standard=extra.get("test_standard", ""),
                            pdf_page=str(page_index + 1),
                            printed_page=printed_page,
                            table_number=table_number,
                            figure_number=figure_number,
                            source_text=snippet[:420],
                            extraction_method="category_reference",
                            confidence="0.44",
                            review_status="UNREVIEWED",
                            engineering_notes="Category-level handbook hit; explicit property labels were not found in the text slice.",
                            data_origin="UNKNOWN",
                        )
                    )
            elif category in {"GENERAL_FATIGUE", "TEMPERATURE_DATA", "EXPERIMENTAL_DATA"}:
                candidates.append(
                    CandidateRow(
                        candidate_id=f"p{page_index + 1:04d}_general_{slugify(category)}",
                        material="",
                        material_condition=extra.get("material_condition", ""),
                        product_form=extra.get("product_form", ""),
                        temperature_C=extra.get("temperature", ""),
                        property_or_data_type=category,
                        property_name=category.lower().replace("_", " "),
                        value="",
                        units="",
                        sigma_max_MPa=extra.get("sigma_max", ""),
                        sigma_min_MPa=extra.get("sigma_min", ""),
                        sigma_a_MPa=extra.get("sigma_a", ""),
                        sigma_m_MPa=extra.get("sigma_m", ""),
                        R_ratio=extra.get("R", ""),
                        strain_amplitude=extra.get("strain_amplitude", ""),
                        life_cycles=extra.get("cycles", ""),
                        reversals="",
                        runout="Yes" if "runout" in text_lower else "",
                        frequency_Hz=extra.get("frequency", ""),
                        strain_rate=extra.get("strain_rate", ""),
                        environment=extra.get("environment", ""),
                        test_standard=extra.get("test_standard", ""),
                        pdf_page=str(page_index + 1),
                        printed_page=printed_page,
                        table_number=table_number,
                        figure_number=figure_number,
                        source_text=snippet[:420],
                        extraction_method="keyword_reference",
                        confidence="0.45",
                        review_status="UNREVIEWED",
                        engineering_notes="General handbook hit; inspect surrounding pages for source context.",
                        data_origin="UNKNOWN",
                    )
                )

        stats["pages_scanned"] += 1
        if progress_every and (page_index + 1) % progress_every == 0:
            print(f"Scanned {page_index + 1}/{doc.page_count} pages; relevant pages so far: {stats['pages_with_hits']}")

    return page_hits, candidates, stats


def context_pages_for_hit(page_number: int, relevance_score: float) -> List[int]:
    radius = 2 if relevance_score >= 80 else 1
    start = max(1, page_number - radius)
    end = page_number + radius
    return list(range(start, end + 1))


def write_context_pages(
    doc,
    output_dir: Path,
    page_hits: Sequence[PageHit],
    source_pdf: Path,
) -> None:
    materials_dir = output_dir / "materials"
    general_dir = output_dir / "general_fatigue"
    seen: Dict[Tuple[str, int], bool] = {}

    grouped: Dict[str, List[PageHit]] = {}
    for hit in page_hits:
        grouped.setdefault(hit.material or "general_fatigue", []).append(hit)

    for material_name, hits in grouped.items():
        folder = general_dir if material_name == "general_fatigue" else materials_dir / slugify(material_name)
        folder.mkdir(parents=True, exist_ok=True)
        pages_dir = folder / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        manifest_rows = []
        for hit in hits:
            for page_number in context_pages_for_hit(hit.pdf_page, hit.relevance_score):
                key = (material_name, page_number)
                if key in seen:
                    continue
                seen[key] = True
                page = doc.load_page(page_number - 1)
                text = collapse_text(page.get_text("text"))
                header = [
                    f"source_pdf: {source_pdf.name}",
                    f"material: {material_name}",
                    f"pdf_page: {page_number}",
                    f"matched_page: {hit.pdf_page}",
                    f"category: {hit.category}",
                    f"relevance_score: {hit.relevance_score}",
                ]
                payload = "\n".join(header) + "\n\n" + text[:4000] + "\n"
                out_path = pages_dir / f"page_{page_number:04d}.txt"
                with out_path.open("w", encoding="utf-8", newline="\n") as fh:
                    fh.write(payload)
                manifest_rows.append(
                    {
                        "pdf_page": page_number,
                        "matched_page": hit.pdf_page,
                        "category": hit.category,
                        "relevance_score": hit.relevance_score,
                        "file": str(out_path.relative_to(output_dir)),
                    }
                )
        if manifest_rows:
            write_csv(folder / "page_manifest.csv", manifest_rows, ["pdf_page", "matched_page", "category", "relevance_score", "file"])


def load_current_database_rows() -> Dict[str, List[dict]]:
    return {
        "materials": read_csv_rows(MATERIAL_DB),
        "static": read_csv_rows(STATIC_DB),
        "fatigue": read_csv_rows(FATIGUE_DB),
        "walker": read_csv_rows(WALKER_DB),
    }


def canonical_material_name(material: str) -> str:
    return normalize_ws(material).lower()


def material_matches_current(material: str, row_material: str) -> bool:
    lhs = canonical_material_name(material)
    rhs = canonical_material_name(row_material)
    if not lhs or not rhs:
        return False
    if lhs == rhs:
        return True
    aliases = DEFAULT_MATERIAL_VARIANTS.get(row_material, [])
    if any(alias in lhs or lhs in alias for alias in aliases):
        return True
    aliases = DEFAULT_MATERIAL_VARIANTS.get(material, [])
    if any(alias in rhs or rhs in alias for alias in aliases):
        return True
    return lhs in rhs or rhs in lhs


def property_family_from_columns(row: dict, source_name: str) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    if source_name == "materials":
        mapping = {
            "E_MPa": "E",
            "S_u_MPa": "S_u",
            "S_y_MPa": "S_y",
            "K_dash": "K'",
            "n_dash": "n'",
            "sigma_f_dash": "sigma_f'",
            "b": "b",
            "epsilon_f_dash": "epsilon_f'",
            "c": "c",
        }
        for column, prop in mapping.items():
            if row.get(column, "").strip():
                entries.append((prop, row[column]))
    elif source_name == "static":
        mapping = {
            "E_MPa": "E",
            "S_u_MPa": "S_u",
            "S_y_MPa": "S_y",
            "mean_CTE_per_C": "CTE",
            "nu": "nu",
            "thermal_conductivity_W_mK": "thermal_conductivity",
            "specific_heat_J_kgK": "specific_heat",
            "density_kg_m3": "density",
        }
        for column, prop in mapping.items():
            if row.get(column, "").strip():
                entries.append((prop, row[column]))
    elif source_name == "fatigue":
        mapping = {
            "K_dash": "K'",
            "n_dash": "n'",
            "sigma_f_dash": "sigma_f'",
            "b": "b",
            "epsilon_f_dash": "epsilon_f'",
            "c": "c",
        }
        for column, prop in mapping.items():
            if row.get(column, "").strip():
                entries.append((prop, row[column]))
    elif source_name == "walker":
        if row.get("Walker_gamma", "").strip():
            entries.append(("Walker_gamma", row["Walker_gamma"]))
    return entries


def property_family_for_name(property_name: str, source_name: str) -> str:
    prop = property_name.lower().strip()
    if prop in {"e", "s_u", "s_y", "nu", "cte", "thermal_conductivity", "specific_heat", "density"}:
        return "STATIC_PROPERTY"
    if prop in {"k'", "n'"}:
        return "CYCLIC_PROPERTY"
    if prop in {"sigma_f'", "b", "epsilon_f'", "c"}:
        return "LCF"
    if prop == "walker_gamma":
        return "MEAN_STRESS"
    if source_name == "walker":
        return "MEAN_STRESS"
    if source_name == "static":
        return "STATIC_PROPERTY"
    if source_name == "fatigue":
        return "LCF"
    return "UNKNOWN"


def property_search_terms(property_name: str, source_name: str) -> List[str]:
    prop = property_name.lower().strip()
    mapping = {
        "e": ["young's modulus", "young modulus", "modulus of elasticity", "elastic modulus"],
        "s_u": ["ultimate tensile strength", "tensile strength", "uts"],
        "s_y": ["yield strength"],
        "nu": ["poisson", "poisson ratio"],
        "cte": ["coefficient of thermal expansion", "thermal expansion", "cte"],
        "thermal_conductivity": ["thermal conductivity"],
        "specific_heat": ["specific heat"],
        "density": ["density"],
        "k'": ["cyclic stress-strain", "ramberg-osgood", "k'"],
        "n'": ["cyclic stress-strain", "ramberg-osgood", "n'"],
        "sigma_f'": ["fatigue strength coefficient", "sigma_f'", "basquin", "strain-life"],
        "b": ["fatigue strength exponent", "basquin"],
        "epsilon_f'": ["fatigue ductility coefficient", "epsilon_f'", "coffin-manson", "strain-life"],
        "c": ["fatigue ductility exponent", "coffin-manson"],
        "walker_gamma": ["walker", "mean stress", "stress ratio", "r ratio", "goodman", "morrow", "swt"],
    }
    if prop in mapping:
        return mapping[prop]
    if source_name == "walker":
        return mapping["walker_gamma"]
    return [prop] if prop else []


def find_best_handbook_candidate(
    material: str,
    current_property: str,
    current_value: str,
    current_temperature: str,
    current_condition: str,
    family: str,
    candidates: Sequence[CandidateRow],
) -> Tuple[str, str, str, str, str, str]:
    material_candidates = [c for c in candidates if c.material and material_matches_current(c.material, material)]
    if current_property == "Walker_gamma":
        ms_candidates = [c for c in material_candidates if c.property_or_data_type == "MEAN_STRESS"]
        if not ms_candidates:
            ms_candidates = [c for c in candidates if c.property_or_data_type == "MEAN_STRESS"]
        if ms_candidates:
            best = ms_candidates[0]
            return (
                best.source_text,
                best.material_condition,
                best.temperature_C,
                best.pdf_page,
                "HANDBOOK_DATA_AVAILABLE_BUT_FIT_REQUIRED",
                "Mean-stress data may support Walker calibration, but no gamma fit is performed here.",
            )
        return ("", "", "", "", "NOT_FOUND", "")

    terms = property_search_terms(current_property, family.lower())
    property_hits = [
        c
        for c in material_candidates
        if c.property_name.lower().strip() == current_property.lower().strip()
        or any(term in c.property_name.lower() for term in terms)
        or any(term in c.property_or_data_type.lower() for term in terms)
        or any(term in c.source_text.lower() for term in terms)
    ]
    if property_hits:
        best = property_hits[0]
        handbook_temp = best.temperature_C.strip()
        current_temp = (current_temperature or "").strip()
        temp_matches = not current_temp or not handbook_temp or handbook_temp == current_temp
        handbook_condition = best.material_condition.strip().lower()
        current_condition_norm = (current_condition or "").strip().lower()
        condition_matches = not current_condition_norm or not handbook_condition or handbook_condition == current_condition_norm
        if best.data_origin == "CURVE_DIGITIZATION_REQUIRED":
            return (
                best.source_text,
                best.material_condition,
                best.temperature_C,
                best.pdf_page,
                "HANDBOOK_CURVE_AVAILABLE",
                "Handbook curve or figure reference located; digitization required before numeric use.",
            )
        if temp_matches and condition_matches:
            return (
                best.source_text,
                best.material_condition,
                best.temperature_C,
                best.pdf_page,
                "DIRECT_MATCH" if best.value else "HANDBOOK_DATA_AVAILABLE_BUT_FIT_REQUIRED",
                "Handbook candidate found for the same property. Verify condition and units.",
            )
        return (
            best.source_text,
            best.material_condition,
            best.temperature_C,
            best.pdf_page,
            "POSSIBLE_MATCH_CONDITION_DIFFERS",
            "Material/property appears in the handbook but the condition or temperature does not line up exactly.",
        )
    family_hits = [c for c in material_candidates if c.property_or_data_type == family]
    if family_hits:
        best = family_hits[0]
        if best.data_origin == "CURVE_DIGITIZATION_REQUIRED":
            return (
                best.source_text,
                best.material_condition,
                best.temperature_C,
                best.pdf_page,
                "HANDBOOK_CURVE_AVAILABLE",
                "Handbook curve or figure reference located; digitization required before numeric use.",
            )
        return (
            best.source_text,
            best.material_condition,
            best.temperature_C,
            best.pdf_page,
            "HANDBOOK_DATA_AVAILABLE_BUT_FIT_REQUIRED",
            "Handbook data exists for the same family, but the exact property was not extracted.",
        )
    if family == "MEAN_STRESS":
        ms_candidates = [c for c in candidates if c.property_or_data_type == "MEAN_STRESS"]
        if ms_candidates:
            best = ms_candidates[0]
            return (
                best.source_text,
                best.material_condition,
                best.temperature_C,
                best.pdf_page,
                "HANDBOOK_DATA_AVAILABLE_BUT_FIT_REQUIRED",
                "General mean-stress data were found in the handbook, but no material-specific gamma value was extracted.",
            )
    return ("", "", "", "", "NOT_FOUND", "")


def build_audit_rows(candidate_rows: Sequence[CandidateRow]) -> List[dict]:
    rows = []
    dbs = load_current_database_rows()
    source_map = [
        ("materials", dbs["materials"]),
        ("static", dbs["static"]),
        ("fatigue", dbs["fatigue"]),
        ("walker", dbs["walker"]),
    ]
    for source_name, source_rows in source_map:
        for row in source_rows:
            material = row.get("Material", "").strip()
            if not material:
                continue
            if material.lower() not in {
                "aluminum 2024-t3",
                "inconel 718",
                "ti-6al-4v",
                "nickel 625",
                "316 stainless steel",
                "aisi 4340",
                "aluminum 7075-t6",
                "haynes 230",
                "rene 41",
            }:
                continue
            for current_property, current_value in property_family_from_columns(row, source_name):
                current_temperature = row.get("Temperature_C") or row.get("property_temperature_C") or ""
                current_condition = row.get("material_condition", "")
                family = property_family_for_name(current_property, source_name)
                handbook_candidate, handbook_condition, handbook_temp, handbook_page, comparison_status, notes = find_best_handbook_candidate(
                    material,
                    current_property,
                    current_value,
                    current_temperature,
                    current_condition,
                    family,
                    candidate_rows,
                )
                current_source = row.get("property_source") or row.get("property_basis") or row.get("gamma_source") or row.get("gamma_basis") or ""
                rows.append(
                    {
                        "material": material,
                        "current_property": current_property,
                        "current_value": current_value,
                        "current_source/basis if available": current_source,
                        "handbook_candidate": handbook_candidate,
                        "handbook_condition": handbook_condition,
                        "handbook_temperature": handbook_temp,
                        "handbook_page": handbook_page,
                        "comparison_status": comparison_status,
                        "notes": notes,
                    }
                )
    return rows


def build_metadata(doc, pdf_path: Path, sample_page_texts: Sequence[Tuple[int, str]]) -> dict:
    return {
        "pdf": pdf_signature(pdf_path),
        "page_count": doc.page_count,
        "document_metadata": doc.metadata,
        "toc_count": len(doc.get_toc()),
        "toc_sample": doc.get_toc()[:20],
        "sample_pages": [
            {
                "pdf_page": page_num,
                "text_length": len(text),
                "text_preview": collapse_text(text[:400]),
            }
            for page_num, text in sample_page_texts
        ],
        "text_searchable": any(len(text.strip()) > 20 for _, text in sample_page_texts),
        "scan_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def sample_document_pages(doc) -> List[Tuple[int, str]]:
    if doc.page_count == 0:
        return []
    picks = sorted({1, 2, 3, max(1, doc.page_count // 2), max(1, doc.page_count - 1), doc.page_count})
    samples = []
    for page_num in picks:
        page = doc.load_page(page_num - 1)
        samples.append((page_num, page.get_text("text")))
    return samples


def write_rows_with_progress(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    write_csv(path, rows, fieldnames)


def summarize(stats: dict, page_hits: Sequence[PageHit], candidates: Sequence[CandidateRow]) -> None:
    unique_pages = len({hit.pdf_page for hit in page_hits})
    print(f"Relevant pages found: {unique_pages}")
    print(f"Candidate rows created: {len(candidates)}")
    if stats["material_hits"]:
        print("Material hits:")
        for material, count in sorted(stats["material_hits"].items(), key=lambda item: (-item[1], item[0])):
            print(f"  {material}: {count}")
    if stats["category_hits"]:
        print("Category hits:")
        for category, count in sorted(stats["category_hits"].items(), key=lambda item: (-item[1], item[0])):
            print(f"  {category}: {count}")


def load_existing_cache(output_dir: Path, pdf_path: Path) -> Optional[Tuple[dict, List[dict], List[dict], List[dict]]]:
    metadata_path = output_dir / "handbook_metadata.json"
    index_path = output_dir / "search_index.csv"
    candidate_path = output_dir / "candidate_data.csv"
    audit_path = output_dir / "fatigue_database_audit.csv"
    metadata = load_cached_json(metadata_path)
    if not metadata:
        return None
    if metadata.get("pdf", {}) != pdf_signature(pdf_path):
        return None
    if not (index_path.exists() and candidate_path.exists() and audit_path.exists()):
        return None
    return (
        metadata,
        read_csv_rows(index_path),
        read_csv_rows(candidate_path),
        read_csv_rows(audit_path),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scan the local ASM Metals Handbook PDF and build fatigue-data mining outputs.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="Local handbook PDF path.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Output directory for index and candidate files.")
    parser.add_argument("--rebuild", action="store_true", help="Force a fresh scan even when a cached index exists.")
    parser.add_argument("--progress-every", type=int, default=50, help="Emit progress every N pages.")
    args = parser.parse_args(argv)

    pdf_path = args.pdf
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    dirs = ensure_output_dirs(args.output_dir)

    if not args.rebuild:
        cached = load_existing_cache(args.output_dir, pdf_path)
        if cached:
            metadata, index_rows, candidate_rows, audit_rows = cached
            print("Cached handbook mining outputs are current; reusing existing index.")
            summarize({"material_hits": {}, "category_hits": {}}, [], [])
            print(f"Index rows: {len(index_rows)}")
            print(f"Candidate rows: {len(candidate_rows)}")
            print(f"Audit rows: {len(audit_rows)}")
            return 0

    if fitz is None:
        print("PyMuPDF is not available. Install it with: python -m pip install pymupdf", file=sys.stderr)
        return 3

    scan_start = time.perf_counter()
    doc = load_pdf(pdf_path)
    try:
        samples = sample_document_pages(doc)
        metadata = build_metadata(doc, pdf_path, samples)
        page_hits, candidate_rows, stats = collect_page_hits(doc, pdf_path, args.progress_every)
        write_context_pages(doc, dirs["base"], page_hits, pdf_path)
        unique_pages = len({hit.pdf_page for hit in page_hits})

        index_rows = [asdict(hit) for hit in page_hits]
        candidate_dicts = [asdict(candidate) for candidate in candidate_rows]
        audit_rows = build_audit_rows(candidate_rows)

        write_rows_with_progress(
            args.output_dir / "search_index.csv",
            index_rows,
            ["pdf_page", "printed_page", "material", "matched_keywords", "category", "relevance_score", "snippet", "source_pdf", "review_status", "notes"],
        )
        write_rows_with_progress(
            args.output_dir / "candidate_data.csv",
            candidate_dicts,
            [
                "candidate_id",
                "material",
                "material_condition",
                "product_form",
                "temperature_C",
                "property_or_data_type",
                "property_name",
                "value",
                "units",
                "sigma_max_MPa",
                "sigma_min_MPa",
                "sigma_a_MPa",
                "sigma_m_MPa",
                "R_ratio",
                "strain_amplitude",
                "life_cycles",
                "reversals",
                "runout",
                "frequency_Hz",
                "strain_rate",
                "environment",
                "test_standard",
                "pdf_page",
                "printed_page",
                "table_number",
                "figure_number",
                "source_text",
                "extraction_method",
                "confidence",
                "review_status",
                "engineering_notes",
                "data_origin",
            ],
        )
        write_rows_with_progress(
            args.output_dir / "fatigue_database_audit.csv",
            audit_rows,
            [
                "material",
                "current_property",
                "current_value",
                "current_source/basis if available",
                "handbook_candidate",
                "handbook_condition",
                "handbook_temperature",
                "handbook_page",
                "comparison_status",
                "notes",
            ],
        )
        save_json(args.output_dir / "handbook_metadata.json", metadata)
        with (args.output_dir / "extraction_log.txt").open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"PDF: {pdf_path}\n")
            fh.write(f"Pages: {doc.page_count}\n")
            fh.write(f"Text searchable: {metadata['text_searchable']}\n")
            fh.write(f"TOC entries: {metadata['toc_count']}\n")
            fh.write(f"Relevant pages: {unique_pages}\n")
            fh.write(f"Candidate rows: {len(candidate_rows)}\n")
            fh.write(f"Audit rows: {len(audit_rows)}\n")
            fh.write(f"Scan seconds: {time.perf_counter() - scan_start:.2f}\n")
            fh.write("Material hits:\n")
            for material, count in sorted(stats["material_hits"].items(), key=lambda item: (-item[1], item[0])):
                fh.write(f"  {material}: {count}\n")
            fh.write("Category hits:\n")
            for category, count in sorted(stats["category_hits"].items(), key=lambda item: (-item[1], item[0])):
                fh.write(f"  {category}: {count}\n")

        print(f"PDF page count: {doc.page_count}")
        print(f"Text extraction works: {metadata['text_searchable']}")
        print(f"Scan time: {time.perf_counter() - scan_start:.2f} s")
        summarize(stats, page_hits, candidate_rows)
        print(f"Outputs written to: {args.output_dir}")
        return 0
    finally:
        doc.close()


if __name__ == "__main__":
    raise SystemExit(main())
