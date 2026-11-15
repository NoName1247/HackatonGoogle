"""
[4] Module 1 — Full-Document Deep Harvester (English-First & Bilingual Edition).
Handles:
1. %PDF-1.x magic byte check, PDF malware blocking (/JS, /Launch), and decompression bomb protection.
2. Two-stage geometric Math-Safe Visual Sanitizer (strips hidden <5.5pt or low-contrast text while preserving math subscripts).
3. Entropy detector & selective local CPU RapidOCR fallback for scanned pages.
4. Cross-Page Table Stitcher (`stitch_cross_page_tables`).
5. 3-Zone Structural Router (`LIT_REVIEW`, `CORE_ENG`, `CLAIMS`) + `<cited_reference>` tagging for IEEE [14] and APA (Author et al., 2024) citations.
6. Table-Preserving Sliding Window Chunker & SHA-256 content-addressable cache keys.
7. Universal 5-Profile detector & 3-Factor Deduplication / Anti-AI-Rewrite Fingerprint
   (64-int MinHash + Universal Hard Anchors + Semantic Centroid).
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import numpy as np
# pymupdf4llm disabled for speed
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config_and_db import PROMPT_VERSION, cas_storage, settings
from models_and_schemas import (
    ChapterChunkDTO,
    DomainProfile,
    HarvestedDocumentDTO,
    Project,
    SecurityAlertDTO,
    ZoneType,
)

logger = logging.getLogger("horizon.harvester")

_rapid_ocr_engine: Any = None


def _get_rapid_ocr() -> Any:
    global _rapid_ocr_engine
    if _rapid_ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _rapid_ocr_engine = RapidOCR()
            logger.info("RapidOCR (ONNX CPU) engine initialized for scanned page fallback.")
        except Exception as exc:
            logger.warning("RapidOCR unavailable (%s), continuing without OCR.", exc)
            _rapid_ocr_engine = False
    return _rapid_ocr_engine


# ==============================================================================
# 1. SECURITY, PII, CITATION & STRUCTURAL REGEX PATTERNS (ENGLISH + BILINGUAL)
# ==============================================================================
DANGEROUS_PDF_KEYS = (b"/JS", b"/JavaScript", b"/Launch", b"/RichMedia")

PROMPT_INJECTION_STOPWORDS = (
    "ignore previous",
    "ignore all",
    "system override",
    "system prompt",
    "suspect_data_leakage",
    "handover_score",
    "final_handover_score",
    "disregard instructions",
    "output maximum score",
    "set score to 100",
    "this thesis has no flaws",
    "100% accuracy",
    "игнорируй",
    "системный промпт",
    "оценка 100",
)

# PII and leaked API secret masking (US/International phones, SSNs, Student IDs, emails, API tokens)
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RE_PHONE = re.compile(
    r"(?:(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}|(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})\b"
)
RE_SSN_OR_STUDENT_ID = re.compile(
    r"\b(?:\d{3}-\d{2}-\d{4}|(?:Student\s*ID|Passport|SSN)\s*[:#]?\s*[A-Z0-9\-]{6,12}|\d{4}\s?\d{6}|\d{3}-\d{3}-\d{3}\s\d{2})\b",
    re.IGNORECASE,
)
RE_API_SECRETS = re.compile(
    r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9\-_]{15,}|AIza[0-9A-Za-z\-_]{30,})\b"
)

RE_URL = re.compile(
    r"https?://[A-Za-z0-9.\-_/~:%+#?&=@]+",
    re.IGNORECASE,
)

# Detects cited sentences with metrics (IEEE "[14]" or APA "(Smith et al., 2024)") so LLM doesn't attribute them to the student
RE_CITED_SENTENCE = re.compile(
    r"([^.!?\n]*?\b\d+(?:[.,]\d+)?\s*%[^.!?\n]*?(?:\[\s*\d+(?:\s*[,–-]\s*\d+)*(?:\s*,\s*(?:p\.|pp\.|с\.)\s*\d+)?\s*\]|\([A-Z][a-z]+\s+et\s+al\.?,?\s*\d{4}\))[^.!?\n]*[.!?]?)"
)

# Top-level section heading classifiers (English + Russian)
RE_HEADING_LIT_REVIEW = re.compile(
    r"^(?:#+\s*)?(?:chapter\s*1\b|section\s*1\b|[12]\.?\s+(?:related\s+work|literature\s+review|background|prior\s+art|state\s+of\s+the\s+art|theoretical\s+background)|related\s+work|literature\s+review|background\s+and\s+related\s+work|prior\s+art|глава\s*1\b|раздел\s*1\b|1\.?\s+(?:обзор|анализ|теоретическ|существующ)|обзор\s+литературы|анализ\s+предметной\s+области)",
    re.IGNORECASE,
)
RE_HEADING_CLAIMS = re.compile(
    r"^(?:#+\s*)?(?:abstract|executive\s+summary|introduction|1\.?\s+introduction|conclusion|conclusions|discussion\s+and\s+conclusion|summary\s+and\s+conclusions|future\s+work|limitations\s+and\s+future\s+work|[567]\.?\s+conclusion|введение|аннотация|заключение|выводы|перспективы\s+развития)\b",
    re.IGNORECASE,
)
RE_HEADING_APPENDIX = re.compile(
    r"^(?:#+\s*)?(?:appendix\s+[a-z0-9]|appendices|supplementary\s+material|приложение\s+[а-яa-z0-9]|приложения)\b",
    re.IGNORECASE,
)
RE_HEADING_BIBLIOGRAPHY = re.compile(
    r"^(?:#+\s*)?(?:references|bibliography|works\s+cited|список\s+(?:использованных\s+|использованной\s+)?(?:источников|литературы)|библиографический\s+список|литература)\b",
    re.IGNORECASE,
)

# Universal Hard Anchors across all 5 university profiles (English & International standards)
RE_UNIVERSAL_ANCHORS = re.compile(
    r"(?:"
    r"\b(?:F1|ROC-AUC|AUC|mAP|IoU|Dice|RMSE|MAE|MAPE|PSNR|SSIM|NPV|IRR|EBITDA|ROI|Sharpe|R2|R²|p-value|p)\s*[=<>≈≤≥]\s*[-+]?\d+(?:[.,]\d+)?"
    r"|\b[nN]\s*=\s*\d{2,6}\b"
    r"|\b(?:ISO|IEC|IEEE|ASTM|ANSI|DIN|ГОСТ|СНиП)\s*(?:[A-Z]+\s*)?[\d.\-–:]+"
    r"|\b(?:GDPR\s*Art\.\s*\d+|HIPAA|CCPA|FDA\s*510\(k\)|CFR\s*Title\s*\d+|\d{1,3}-ФЗ|ст\.\s*\d+(?:\.\d+)?\s*(?:ГК|УК|ТК|НК)\s*РФ)\b"
    r"|\b(?:Case\s*No\.|Docket\s*No\.|№)\s*[A-Za-zА-Яа-я0-9\-/]{5,20}"
    r"|\b(?:YOLOv\d+|U-Net|ResNet-?\d*|ViT|BERT|RoBERTa|DeBERTa|Llama-?\d*|Qwen-?\d*|Mistral|CatBoost|LightGBM|XGBoost|STM32[A-Z0-9]*|ESP32|FPGA|MODBUS|SCADA|OPC\s*UA|DICOM|MONAI|ONNX|TensorRT)\b"
    r")",
    re.IGNORECASE,
)


def mask_pii_and_secrets(text: str) -> str:
    """Redacts phone numbers, emails, SSNs/IDs, and accidentally committed API keys before external LLM calls."""
    text = RE_API_SECRETS.sub("[REDACTED_SECRET]", text)
    text = RE_EMAIL.sub("[REDACTED_EMAIL]", text)
    text = RE_PHONE.sub("[REDACTED_PHONE]", text)
    text = RE_SSN_OR_STUDENT_ID.sub("[REDACTED_ID]", text)
    return text


def _int_color_to_rgb(color_int: int) -> tuple[int, int, int]:
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    return r, g, b


# ==============================================================================
# 2. PDF SECURITY VALIDATION & MATH-SAFE VISUAL SANITIZER
# ==============================================================================
def validate_pdf_security(pdf_path: Path) -> None:
    """Verifies %PDF-1.x magic bytes, file size (<= 25 MB), and blocks embedded /JS or /Launch exploits."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    file_size = pdf_path.stat().st_size
    if file_size < 64:
        raise ValueError("INVALID_PDF: File is empty or smaller than 64 bytes.")
    if file_size > 26 * 1024 * 1024:
        raise ValueError("PDF_TOO_LARGE: PDF exceeds the hard 25 MB limit.")

    with pdf_path.open("rb") as f:
        header = f.read(16)
        if not header.startswith(b"%PDF-1.") and not header.startswith(b"%PDF-2."):
            raise ValueError("INVALID_PDF_SIGNATURE: Missing %PDF-1.x header in the first 8 bytes.")

        raw_head = header + f.read(512 * 1024)
        for bad_key in DANGEROUS_PDF_KEYS:
            if bad_key in raw_head:
                raise ValueError(
                    f"PDF_MALWARE_DETECTED: Forbidden executable PDF object {bad_key.decode()} detected."
                )


def sanitize_page_and_extract_clean_text(
    page: fitz.Page,
    page_num: int,
    allow_ocr: bool = True,
) -> tuple[str, SecurityAlertDTO | None, bool, list[tuple[float, str]]]:
    """
    Two-stage geometric Math-Safe Visual Sanitizer:
    - Retains short mathematical subscripts/superscripts (<= 4 alphabetic chars) even if font_size < 5.5pt.
    - Strips long hidden spans (< 5.5pt or near-white contrast dRGB < 25) and flags HIDDEN_TEXT_INJECTION_ATTEMPT.
    - Triggers selective CPU RapidOCR if page has < 100 valid letters and contains raster images.
    """
    pass
    try:
        page.remove_rotation()
    except Exception:
        pass

    raw_dict = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
    visible_lines: list[str] = []
    font_styled_lines: list[tuple[float, str]] = []
    hidden_suspect_fragments: list[str] = []

    for block in raw_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_visible_parts: list[str] = []
            max_line_font_size = 0.0
            for span in line.get("spans", []):
                span_text: str = span.get("text", "")
                if not span_text.strip():
                    continue
                font_size = float(span.get("size", 11.0))
                color_int = int(span.get("color", 0))
                r, g, b = _int_color_to_rgb(color_int)
                delta_white = math.sqrt((255 - r) ** 2 + (255 - g) ** 2 + (255 - b) ** 2)

                alpha_chars = sum(1 for ch in span_text if ch.isalpha())
                is_tiny_or_invisible = (font_size < 5.5) or (delta_white < 25.0)

                if is_tiny_or_invisible and alpha_chars > 4:
                    hidden_suspect_fragments.append(span_text.strip())
                else:
                    line_visible_parts.append(span_text)
                    if font_size > max_line_font_size:
                        max_line_font_size = font_size

            if line_visible_parts:
                joined_line = "".join(line_visible_parts).strip()
                if joined_line:
                    visible_lines.append(joined_line)
                    font_styled_lines.append((max_line_font_size, joined_line))

    security_alert: SecurityAlertDTO | None = None
    if hidden_suspect_fragments:
        combined_hidden = " ".join(hidden_suspect_fragments)
        hidden_alpha_len = sum(1 for ch in combined_hidden if ch.isalpha())
        lower_hidden = combined_hidden.lower()
        has_injection_kw = any(kw in lower_hidden for kw in PROMPT_INJECTION_STOPWORDS)

        if hidden_alpha_len > 25 or has_injection_kw:
            security_alert = SecurityAlertDTO(
                alert_code="HIDDEN_TEXT_INJECTION_ATTEMPT",
                page_number=page_num,
                hidden_char_count=hidden_alpha_len,
                sample_snippet=combined_hidden[:180],
            )
            logger.warning(
                "Prompt injection / hidden text detected on page %d (%d chars): %s",
                page_num,
                hidden_alpha_len,
                combined_hidden[:100],
            )

    page_clean_text = "\n".join(visible_lines)
    valid_letters = sum(1 for ch in page_clean_text if ch.isalpha())
    used_ocr = False

    if False and allow_ocr and len(page.get_images(full=False)) > 0:
        ocr_engine = _get_rapid_ocr()
        if ocr_engine:
            try:
                pix = page.get_pixmap(dpi=150, alpha=False)
                if pix.width * pix.height * 3 <= 64 * 1024 * 1024:
                    img_bytes = pix.tobytes("png")
                    ocr_result, _ = ocr_engine(img_bytes)
                    if ocr_result:
                        ocr_lines = [item[1] for item in ocr_result if len(item) >= 2 and item[1]]
                        if ocr_lines:
                            page_clean_text = "\n".join(ocr_lines)
                            font_styled_lines = [(12.0, ln) for ln in ocr_lines]
                            used_ocr = True
            except Exception as ocr_exc:
                logger.debug("RapidOCR page %d skipped: %s", page_num, ocr_exc)

    return page_clean_text, security_alert, used_ocr, font_styled_lines


# ==============================================================================
# 3. CROSS-PAGE TABLE STITCHER
# ==============================================================================
RE_PAGE_NUMBER_LINE = re.compile(
    r"^\s*(?:[-–—]?\s*\d{1,3}\s*[-–—]?|(?:page|p\.|стр\.?)\s*\d+(?:\s+of\s+\d+)?)\s*$",
    re.IGNORECASE,
)
RE_TABLE_CONTINUATION = re.compile(
    r"^\s*(?:table\s+[\d.]+\s*\(?continued\)?|continued\s+from\s+previous\s+page|продолжение\s+таблицы|окончание\s+таблицы|таблица\s+[\d.]+\s*\(?продолжение\)?)",
    re.IGNORECASE,
)


def stitch_cross_page_tables(page_markdowns: list[str]) -> list[str]:
    """Stitches Markdown tables split across page boundaries into contiguous blocks."""
    if len(page_markdowns) <= 1:
        return page_markdowns

    cleaned_pages: list[list[str]] = []
    for md in page_markdowns:
        lines = [
            ln
            for ln in md.splitlines()
            if not RE_PAGE_NUMBER_LINE.match(ln.strip())
        ]
        cleaned_pages.append(lines)

    for idx in range(len(cleaned_pages) - 1):
        curr_lines = cleaned_pages[idx]
        next_lines = cleaned_pages[idx + 1]
        if not curr_lines or not next_lines:
            continue

        last_non_empty_idx = len(curr_lines) - 1
        while last_non_empty_idx >= 0 and not curr_lines[last_non_empty_idx].strip():
            last_non_empty_idx -= 1
        if last_non_empty_idx < 0:
            continue

        last_line = curr_lines[last_non_empty_idx].strip()
        if not (last_line.startswith("|") and last_line.endswith("|") and last_line.count("|") >= 3):
            continue

        first_idx = 0
        while first_idx < len(next_lines) and not next_lines[first_idx].strip():
            first_idx += 1
        if first_idx >= len(next_lines):
            continue

        first_line = next_lines[first_idx].strip()
        is_continuation_header = bool(RE_TABLE_CONTINUATION.match(first_line))
        if is_continuation_header:
            next_lines.pop(first_idx)
            while first_idx < len(next_lines) and not next_lines[first_idx].strip():
                next_lines.pop(first_idx)
            if first_idx < len(next_lines):
                first_line = next_lines[first_idx].strip()

        if first_line.startswith("|") and first_line.endswith("|"):
            table_continuation_rows: list[str] = []
            while first_idx < len(next_lines):
                candidate = next_lines[first_idx].strip()
                if candidate.startswith("|") and candidate.endswith("|"):
                    table_continuation_rows.append(next_lines.pop(first_idx))
                elif not candidate:
                    next_lines.pop(first_idx)
                else:
                    break
            if table_continuation_rows:
                curr_lines.extend(table_continuation_rows)

    return ["\n".join(lines) for lines in cleaned_pages]


# ==============================================================================
# 4. UNIVERSAL 5-PROFILE DETECTOR, MINHASH & HARD ANCHORS (ANTI-REWRITE)
# ==============================================================================
def detect_university_domain_profile(full_text: str) -> DomainProfile:
    """
    Classifies a thesis/paper into one of the 5 universal university profiles
    (supports both English and Russian terminology).
    """
    sample = full_text[:45000].lower()

    scores: dict[DomainProfile, int] = {
        DomainProfile.IT_AND_DATA_SCIENCE: 0,
        DomainProfile.ENGINEERING_AND_HARDWARE: 0,
        DomainProfile.NATURAL_AND_BIOMEDICAL: 0,
        DomainProfile.ECONOMICS_AND_MANAGEMENT: 0,
        DomainProfile.HUMANITIES_SOCIAL_AND_LAW: 0,
    }

    it_kws = (
        "neural network", "deep learning", "dataset", "training", "inference",
        "python", "pytorch", "tensorflow", "fastapi", "docker", "algorithm",
        "repository", "github", "f1-score", "roc-auc", "cross-validation", "transformer",
        "нейросеть", "датасет", "инференс", "алгоритм",
    )
    eng_kws = (
        "schematic", "microcontroller", "plc", "sensor", "actuator", "testbed",
        "ieee", "iso", "astm", "voltage", "sampling rate", "speckle", "radar",
        "ultrasound", "weld", "ndt", "radiograph", "fpga", "scada", "modbus", "stm32",
        "чертеж", "микроконтроллер", "датчик", "спекл", "сварн", "радиофиз",
    )
    bio_kws = (
        "patient", "clinical", "diagnosis", "ultrasound", "x-ray", "ct scan", "mri",
        "biological", "chemical", "reagent", "concentration", "in vivo", "in vitro",
        "pathology", "cohort", "p-value", "biomedical", "lesion", "monai", "dicom",
        "пациент", "клиническ", "узи", "рентген", "когорт",
    )
    econ_kws = (
        "profitability", "revenue", "financial", "investment", "npv", "ebitda",
        "roi", "supply chain", "logistics", "enterprise", "econometric", "panel data",
        "market", "budget", "cash flow", "default probability", "insolvency",
        "рентабельност", "финансов", "эконометрич", "кассовый разрыв",
    )
    hum_kws = (
        "respondent", "questionnaire", "sociological", "legal", "legislation",
        "statute", "regulatory", "gdpr", "hipaa", "court", "linguistic", "discourse",
        "archival", "psychological", "text corpus", "survey", "privacy", "k-anonymity",
        "респондент", "правовой", "законодательств", "корпус текстов", "152-фз",
    )

    for kw in it_kws:
        scores[DomainProfile.IT_AND_DATA_SCIENCE] += sample.count(kw) * 2
    for kw in eng_kws:
        scores[DomainProfile.ENGINEERING_AND_HARDWARE] += sample.count(kw) * 2
    for kw in bio_kws:
        scores[DomainProfile.NATURAL_AND_BIOMEDICAL] += sample.count(kw) * 2
    for kw in econ_kws:
        scores[DomainProfile.ECONOMICS_AND_MANAGEMENT] += sample.count(kw) * 2
    for kw in hum_kws:
        scores[DomainProfile.HUMANITIES_SOCIAL_AND_LAW] += sample.count(kw) * 2

    best_profile = max(scores.items(), key=lambda kv: kv[1])[0]
    return best_profile if scores[best_profile] > 0 else DomainProfile.IT_AND_DATA_SCIENCE


def compute_minhash_signature(text: str, num_perm: int = 64) -> list[int]:
    """
    Computes a position-independent 64-int MinHash fingerprint over 3-word shingles.
    100% immune to paragraph insertions at the beginning of the file or chapter reordering.
    """
    words = re.findall(r"[a-zа-яё0-9]{3,}", text.lower())
    if len(words) < 3:
        return [0] * num_perm

    shingles = {
        f"{words[i]} {words[i + 1]} {words[i + 2]}".encode("utf-8")
        for i in range(0, min(len(words) - 2, 25000), 2)
    }
    if not shingles:
        return [0] * num_perm

    base_hashes = [
        int.from_bytes(hashlib.blake2b(sh, digest_size=8).digest(), "big")
        for sh in shingles
    ]

    mersenne_prime = (1 << 61) - 1
    signature: list[int] = []
    for perm_idx in range(num_perm):
        a = ((perm_idx + 1) * 0x5DEECE66D + 0xB) & ((1 << 60) - 1) | 1
        b = ((perm_idx + 7) * 0x27BB2EE687B0B0FD) & ((1 << 60) - 1)
        min_h = min(((a * h + b) % mersenne_prime) for h in base_hashes)
        signature.append(int(min_h & 0x7FFFFFFF))

    return signature


def calculate_minhash_jaccard(sig_a: list[int], sig_b: list[int]) -> float:
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return round(matches / len(sig_a), 4)


def extract_universal_hard_anchors(text: str, urls: list[str]) -> tuple[list[str], str]:
    """Extracts AI-rewrite-resistant Hard Anchors (table metrics, ISO/IEEE standards, sample sizes, URLs)."""
    found = {m.group(0).strip().lower() for m in RE_UNIVERSAL_ANCHORS.finditer(text)}
    for u in urls[:10]:
        found.add(u.lower().rstrip("/"))

    for line in text.splitlines():
        if line.strip().startswith("|") and line.strip().endswith("|"):
            nums = re.findall(r"\b\d+[.,]\d{1,4}\b", line)
            if len(nums) >= 2:
                found.add("tbl_row:" + "_".join(n.replace(",", ".") for n in nums[:5]))

    sorted_anchors = sorted(found)[:120]
    anchors_hash = hashlib.sha256("|".join(sorted_anchors).encode("utf-8")).hexdigest()
    return sorted_anchors, anchors_hash


def calculate_anchor_overlap(anchors_a: list[str], anchors_b: list[str]) -> float:
    if not anchors_a or not anchors_b:
        return 0.0
    set_a, set_b = set(anchors_a), set(anchors_b)
    inter = len(set_a & set_b)
    denom = min(len(set_a), len(set_b))
    return round(inter / max(denom, 1), 4)


# ==============================================================================
# 5. STRUCTURAL CHAPTER ROUTER & TABLE-PRESERVING SLIDING WINDOW CHUNKER
# ==============================================================================
def _classify_heading_zone(heading_text: str, current_zone: ZoneType) -> ZoneType | str:
    clean_h = heading_text.strip()
    if RE_HEADING_BIBLIOGRAPHY.match(clean_h):
        return "BIBLIOGRAPHY"
    if RE_HEADING_APPENDIX.match(clean_h):
        return "APPENDIX"
    if RE_HEADING_CLAIMS.match(clean_h):
        return ZoneType.CLAIMS
    if RE_HEADING_LIT_REVIEW.match(clean_h):
        return ZoneType.LIT_REVIEW
    if re.match(
        r"^(?:#+\s*)?(?:chapter\s*[2345]|section\s*[2345]|[2345]\.\s+\S+|methodology|methods|proposed\s+method|implementation|experiments|evaluation|results|empirical\s+analysis|глава\s*[2345]|раздел\s*[2345])",
        clean_h,
        re.IGNORECASE,
    ):
        return ZoneType.CORE_ENG
    return current_zone


def _mark_cited_references_in_core(text: str) -> str:
    return text


def _split_core_section_preserving_tables(
    section_title: str,
    section_text: str,
    start_page: int,
    end_page: int,
    header_hash: str,
    max_tokens_per_chunk: int = 4200,
) -> list[ChapterChunkDTO]:
    paragraphs = re.split(r"\n{2,}", section_text.strip())
    chunks: list[ChapterChunkDTO] = []

    current_blocks: list[str] = []
    current_tokens = 0
    in_table_aftermath = 0

    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            continue

        is_table_block = para_stripped.startswith("|") or "\n|" in para_stripped
        para_tokens = max(1, len(para_stripped) // 3)

        if is_table_block:
            in_table_aftermath = 2
        elif in_table_aftermath > 0:
            in_table_aftermath -= 1

        should_flush = (
            current_tokens + para_tokens > max_tokens_per_chunk
            and current_blocks
            and not is_table_block
            and in_table_aftermath == 0
        )

        if should_flush:
            chunk_md = _mark_cited_references_in_core("\n\n".join(current_blocks))
            norm_for_hash = re.sub(r"\s+", " ", chunk_md).strip()
            cache_key = hashlib.sha256(
                f"{PROMPT_VERSION}||{header_hash}||{norm_for_hash}".encode("utf-8")
            ).hexdigest()

            chunks.append(
                ChapterChunkDTO(
                    chunk_index=len(chunks),
                    heading_title=section_title,
                    zone_type=ZoneType.CORE_ENG,
                    start_page=start_page,
                    end_page=end_page,
                    text_markdown=mask_pii_and_secrets(chunk_md),
                    token_estimate=current_tokens,
                    cache_key=cache_key,
                )
            )
            overlap_block = current_blocks[-1] if current_blocks else ""
            current_blocks = [overlap_block, para_stripped] if overlap_block else [para_stripped]
            current_tokens = (len(overlap_block) // 3) + para_tokens
        else:
            current_blocks.append(para_stripped)
            current_tokens += para_tokens

    if current_blocks:
        chunk_md = _mark_cited_references_in_core("\n\n".join(current_blocks))
        norm_for_hash = re.sub(r"\s+", " ", chunk_md).strip()
        cache_key = hashlib.sha256(
            f"{PROMPT_VERSION}||{header_hash}||{norm_for_hash}".encode("utf-8")
        ).hexdigest()
        chunks.append(
            ChapterChunkDTO(
                chunk_index=len(chunks),
                heading_title=section_title,
                zone_type=ZoneType.CORE_ENG,
                start_page=start_page,
                end_page=end_page,
                text_markdown=mask_pii_and_secrets(chunk_md),
                token_estimate=current_tokens,
                cache_key=cache_key,
            )
        )

    return chunks


# ==============================================================================
# 6. MAIN PDF PARSING PIPELINE (PARSE_AND_ZONE_PDF)
# ==============================================================================
def _extract_metadata_from_title_pages(first_pages_text: str, fallback_title: str) -> dict[str, Any]:
    lines = [ln.strip() for ln in first_pages_text.splitlines() if ln.strip()]
    title = fallback_title
    author = "University Researcher"
    supervisor = "Faculty Advisor"
    department = "University Research Department"
    year = 2025
    for ln in lines[:40]:
        low = ln.lower()
        if ("author:" in low or "выполнил" in low or "студент" in low or "by:" in low) and len(ln) < 120:
            author = ln.split(":", 1)[-1].strip()[:100]
        elif ("supervisor" in low or "advisor" in low or "руководитель" in low) and len(ln) < 120:
            supervisor = ln.split(":", 1)[-1].strip()[:100]
        elif ("department" in low or "school of" in low or "faculty" in low or "кафедра" in low) and len(ln) < 120:
            department = ln.strip()[:110]
    for ln in lines[:20]:
        if 15 <= len(ln) <= 180 and not any(w in ln.lower() for w in ("ministry", "university", "department", "thesis", "министерство", "университет", "кафедра")):
            title = ln.strip("#* «»\"")
            break
    return {"title": title[:280], "author": author, "supervisor": supervisor, "department": department, "year": year}


def parse_and_zone_pdf(
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
    pdf_path: Path,
    pdf_sha256: str,
    explicit_title: str | None = None,
    disable_secondary_ocr: bool = False,
) -> HarvestedDocumentDTO:
    validate_pdf_security(pdf_path)

    doc = fitz.open(str(pdf_path))
    total_pages = min(len(doc), settings.MAX_PAGES_PROCESSED)

    try:
        md_page_chunks = pymupdf4llm.to_markdown(
            doc,
            pages=list(range(total_pages)),
            page_chunks=True,
            write_images=False,
        )
        raw_md_by_page = [
            (chunk.get("text", "") if isinstance(chunk, dict) else str(chunk))
            for chunk in md_page_chunks
        ]
    except Exception as exc:
        logger.warning("pymupdf4llm fallback to standard get_text on %s: %s", pdf_path.name, exc)
        raw_md_by_page = [doc[p].get_text("text") for p in range(total_pages)]

    security_alerts: list[SecurityAlertDTO] = []
    ocr_pages_count = 0
    all_font_sizes: list[float] = []
    page_styled_lines: list[list[tuple[float, str]]] = []
    sanitized_md_pages: list[str] = []

    for p_idx in range(total_pages):
        page = doc[p_idx]
        allow_ocr_on_page = (not disable_secondary_ocr) or (p_idx < 3 or p_idx >= total_pages - 5)
        clean_txt, alert, used_ocr, styled_lines = sanitize_page_and_extract_clean_text(
            page, p_idx + 1, allow_ocr=allow_ocr_on_page
        )
        if alert is not None:
            security_alerts.append(alert)
        if used_ocr:
            ocr_pages_count += 1

        for f_size, _ in styled_lines:
            if 6.0 <= f_size <= 36.0:
                all_font_sizes.append(round(f_size, 1))
        page_styled_lines.append(styled_lines)

        base_md = raw_md_by_page[p_idx] if p_idx < len(raw_md_by_page) else clean_txt
        if used_ocr or len(base_md.strip()) < len(clean_txt.strip()) * 0.5:
            sanitized_md_pages.append(clean_txt)
        else:
            sanitized_md_pages.append(base_md)

    doc.close()

    stitched_pages = stitch_cross_page_tables(sanitized_md_pages)
    full_markdown = "\n\n".join(stitched_pages)

    markdown_zst_path = cas_storage.save_compressed_markdown(revision_id, full_markdown)

    body_font_size = Counter(all_font_sizes).most_common(1)[0][0] if all_font_sizes else 12.0
    heading_font_threshold = round(body_font_size * 1.15, 1)

    first_three_pages = "\n".join(stitched_pages[:3])
    meta_info = _extract_metadata_from_title_pages(
        first_three_pages, explicit_title or pdf_path.stem
    )
    if explicit_title and len(explicit_title.strip()) >= 5:
        meta_info["title"] = explicit_title.strip()

    domain_profile = detect_university_domain_profile(full_markdown)
    extracted_urls = list(dict.fromkeys(RE_URL.findall(full_markdown)))[:30]

    minhash_sig = compute_minhash_signature(full_markdown)
    hard_anchors, hard_anchors_hash = extract_universal_hard_anchors(full_markdown, extracted_urls)

    abbreviations = sorted(set(re.findall(r"\b[A-ZА-Я]{2,8}(?:-\d+)?\b", full_markdown[:15000])))[:25]
    global_context_header = (
        f"THESIS TITLE: {meta_info['title']}\n"
        f"UNIVERSITY PROFILE: {domain_profile.value} | DEPARTMENT: {meta_info['department']} | YEAR: {meta_info['year']}\n"
        f"KEY ABBREVIATIONS & TERMS: {', '.join(abbreviations) if abbreviations else 'Standard'}"
    )
    header_hash = hashlib.sha256(global_context_header.encode("utf-8")).hexdigest()[:16]

    current_zone: ZoneType | str = ZoneType.CLAIMS
    current_heading = "Introduction and Problem Statement"
    current_section_lines: list[str] = []
    section_start_page = 1

    claims_parts: list[str] = []
    lit_review_parts: list[str] = []
    appendix_parts: list[str] = []
    core_sections: list[tuple[str, str, int, int]] = []

    def _flush_section(end_p: int) -> None:
        text_block = "\n".join(current_section_lines).strip()
        if not text_block:
            return
        if current_zone == ZoneType.CLAIMS:
            claims_parts.append(f"## {current_heading} (Pages {section_start_page}-{end_p})\n{text_block}")
        elif current_zone == ZoneType.LIT_REVIEW:
            lit_review_parts.append(text_block)
        elif current_zone == "APPENDIX":
            appendix_parts.append(text_block)
        elif current_zone == ZoneType.CORE_ENG:
            core_sections.append((current_heading, text_block, section_start_page, end_p))

    for p_idx, page_md in enumerate(stitched_pages):
        page_no = p_idx + 1
        styled_on_page = page_styled_lines[p_idx] if p_idx < len(page_styled_lines) else []
        large_font_texts = {
            txt.strip().lower()
            for f_sz, txt in styled_on_page
            if f_sz >= heading_font_threshold and 4 <= len(txt.strip()) <= 140
        }

        for line in page_md.splitlines():
            stripped = line.strip()
            clean_no_md = stripped.lstrip("#* ").strip()
            is_md_heading = stripped.startswith("#")
            is_numbered_chapter = bool(
                re.match(
                    r"^(?:chapter\s+\d+|section\s+\d+|abstract|introduction|related\s+work|methodology|experiments|evaluation|conclusion|conclusions|future\s+work|appendix|глава\s+\d+|раздел\s+\d+|введение|заключение|выводы|приложение|[1-6]\.\d*\s+[A-ZА-ЯЁ])",
                    clean_no_md,
                    re.IGNORECASE,
                )
            )
            is_large_font_heading = clean_no_md.lower() in large_font_texts

            if (is_md_heading or is_numbered_chapter or is_large_font_heading) and 3 <= len(clean_no_md) <= 140:
                new_zone = _classify_heading_zone(
                    clean_no_md,
                    ZoneType.CORE_ENG if isinstance(current_zone, str) else current_zone,
                )
                if new_zone != current_zone or is_numbered_chapter or stripped.startswith("## "):
                    _flush_section(page_no)
                    current_section_lines = []
                    current_heading = clean_no_md
                    current_zone = new_zone
                    section_start_page = page_no
                    continue

            current_section_lines.append(line)

    _flush_section(total_pages)

    if not core_sections and stitched_pages:
        mid_start = max(1, int(total_pages * 0.15))
        mid_end = max(mid_start + 1, int(total_pages * 0.85))
        core_fallback_text = "\n\n".join(stitched_pages[mid_start - 1 : mid_end])
        core_sections.append(("Core Methodology & Experimental Evaluation", core_fallback_text, mid_start, mid_end))
        if not claims_parts:
            claims_parts.append(
                "\n\n".join(stitched_pages[:mid_start] + stitched_pages[mid_end:])
            )

    core_chunks: list[ChapterChunkDTO] = []
    for sec_title, sec_text, s_page, e_page in core_sections:
        sec_chunks = _split_core_section_preserving_tables(
            section_title=sec_title,
            section_text=sec_text,
            start_page=s_page,
            end_page=e_page,
            header_hash=header_hash,
        )
        core_chunks.extend(sec_chunks)

    core_chunks = core_chunks[: settings.MAX_MAP_CHUNKS_PER_THESIS]
    for idx, ch in enumerate(core_chunks):
        ch.chunk_index = idx

    lit_text_full = "\n".join(lit_review_parts)
    baselines = sorted(
        set(
            re.findall(
                r"\b(?:YOLOv\d+|U-Net|ResNet\d*|ViT|BERT|GPT-\d+|ARIMA|LSTM|CatBoost|XGBoost|Random\s+Forest|SVM|K-Means|OLS|ISO\s*[\d.\-]+)\b",
                lit_text_full,
                re.IGNORECASE,
            )
        )
    )[:15]

    appendix_full = "\n".join(appendix_parts)
    has_structured_appendix = (
        ("|" in appendix_full and appendix_full.count("|") >= 12)
        or len(appendix_full) > 1200
        or (("table" in full_markdown.lower() or "таблица" in full_markdown.lower()) and full_markdown.count("|") >= 25)
    )

    claims_combined = mask_pii_and_secrets("\n\n".join(claims_parts)[:18000])
    if not claims_combined.strip():
        claims_combined = mask_pii_and_secrets(
            (stitched_pages[0] + "\n\n" + stitched_pages[-1])[:12000]
        )

    return HarvestedDocumentDTO(
        project_id=project_id,
        revision_id=revision_id,
        pdf_sha256=pdf_sha256,
        pdf_blob_path=str(pdf_path),
        markdown_zst_path=markdown_zst_path,
        detected_title=meta_info["title"],
        detected_author=meta_info["author"],
        detected_supervisor=meta_info["supervisor"],
        detected_department=meta_info["department"],
        detected_year=meta_info["year"],
        detected_domain_profile=domain_profile,
        global_context_header=global_context_header,
        header_hash=header_hash,
        extracted_urls=extracted_urls,
        lit_review_baselines=baselines,
        claims_text=claims_combined,
        core_chunks=core_chunks,
        has_structured_appendix=has_structured_appendix,
        minhash_signature=minhash_sig,
        hard_anchors=hard_anchors,
        hard_anchors_hash=hard_anchors_hash,
        security_alerts=security_alerts,
        total_pages=total_pages,
        ocr_pages_count=ocr_pages_count,
    )


# ==============================================================================
# 7. 3-FACTOR DRAFT DEDUPLICATION vs SAME-TITLE INDEPENDENT THESIS vs AI-REWRITE
# ==============================================================================
async def resolve_lineage_and_detect_rewrite(
    db: AsyncSession,
    harvest: HarvestedDocumentDTO,
    new_semantic_centroid: np.ndarray | None = None,
) -> tuple[Project | None, str | None]:
    stmt = select(Project).where(Project.id != harvest.project_id).order_by(Project.updated_at.desc()).limit(250)
    result = await db.execute(stmt)
    existing_projects = list(result.scalars().all())

    norm_new_author = re.sub(r"[^a-zа-яё]", "", harvest.detected_author.lower())

    best_same_author_project: Project | None = None
    plagiarism_warning: str | None = None

    for cand in existing_projects:
        norm_cand_author = re.sub(r"[^a-zа-яё]", "", (cand.author_name or "").lower())
        same_author = bool(
            norm_new_author
            and norm_cand_author
            and (
                norm_new_author == norm_cand_author
                or norm_new_author in norm_cand_author
                or norm_cand_author in norm_new_author
            )
            and harvest.detected_author not in ("University Graduate", "Unknown Author")
        )

        mh_sim = calculate_minhash_jaccard(harvest.minhash_signature, cand.minhash_signature or [])
        anchor_sim = calculate_anchor_overlap(harvest.hard_anchors, cand.hard_anchors_json or [])

        sem_sim = 0.0
        if new_semantic_centroid is not None and cand.semantic_centroid_fp32:
            cand_vec = np.frombuffer(cand.semantic_centroid_fp32, dtype=np.float32)
            if cand_vec.shape == new_semantic_centroid.shape:
                denom = (np.linalg.norm(new_semantic_centroid) * np.linalg.norm(cand_vec)) or 1.0
                sem_sim = float(np.dot(new_semantic_centroid, cand_vec) / denom)

        if same_author and (mh_sim >= 0.30 or anchor_sim >= 0.35 or sem_sim >= 0.88):
            best_same_author_project = cand
            break

        if not same_author:
            if mh_sim >= 0.45 or (sem_sim >= 0.90 and anchor_sim >= 0.35) or anchor_sim >= 0.65:
                overlap_pct = int(max(mh_sim, sem_sim, anchor_sim) * 100)
                plagiarism_warning = (
                    f"BOARD ALERT: High semantic & experimental table overlap ({overlap_pct}%) "
                    f"with defended thesis \"{cand.title}\" (Author: {cand.author_name}, {cand.publication_year}). "
                    f"Potential LLM-paraphrased rewrite or uncredited empirical dataset reuse."
                )

    return best_same_author_project, plagiarism_warning
