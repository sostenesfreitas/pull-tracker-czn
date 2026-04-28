# parser.py — OCR + detecção de raridade por nome (lookup) com fallback por cor

import difflib
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image

from . import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Tesseract
# ──────────────────────────────────────────────────────────────

def _setup_tesseract() -> None:
    """Localiza o Tesseract: config → caminhos padrão Windows → PATH."""
    import shutil

    if config.TESSERACT_CMD and os.path.isfile(config.TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
        logger.debug("Tesseract configurado: %s", config.TESSERACT_CMD)
        return

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info("Tesseract encontrado: %s", path)
            return

    if shutil.which("tesseract"):
        logger.info("Tesseract encontrado no PATH do sistema.")
        return

    logger.error(
        "Tesseract não encontrado! Instale em:\n"
        "  https://github.com/UB-Mannheim/tesseract/wiki\n"
        "  Ou defina TESSERACT_CMD no config.py"
    )

_setup_tesseract()


# ──────────────────────────────────────────────────────────────
# Lookup de raridade por nome  (fonte principal)
# ──────────────────────────────────────────────────────────────

def _load_character_db() -> Dict[str, int]:
    """
    Carrega characters.json e retorna dict {nome_lower: raridade}.
    Também guarda os nomes originais para corrigir o OCR depois.
    """
    path = config.CHARACTERS_FILE
    if not os.path.isfile(path):
        logger.warning("characters.json não encontrado em: %s", path)
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    db = {entry["name"].lower(): entry["rarity"] for entry in data}
    logger.info("Lookup carregado: %d personagens.", len(db))
    return db

# Nomes originais para exibição correta
def _load_canonical_names() -> Dict[str, str]:
    """Retorna {nome_lower: nome_original}."""
    path = config.CHARACTERS_FILE
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {entry["name"].lower(): entry["name"] for entry in data}

def _load_meta_db() -> Dict[str, dict]:
    """Retorna {nome_lower: {image, class, attribute}} para uso no frontend."""
    path = config.CHARACTERS_FILE
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        entry["name"].lower(): {
            "image":     entry.get("image"),
            "class":     entry.get("class"),
            "attribute": entry.get("attribute"),
        }
        for entry in data
    }

_CHAR_DB: Dict[str, int] = _load_character_db()
_CANONICAL: Dict[str, str] = _load_canonical_names()
_META_DB: Dict[str, dict] = _load_meta_db()
_KNOWN_NAMES: List[str] = list(_CHAR_DB.keys())


def lookup_character(raw_name: str) -> Tuple[int, str, Optional[str], Optional[str], Optional[str], str]:
    """
    Resolve raridade, nome canônico, imagem, classe e atributo pelo nome OCR.

    Estratégia:
    1. Match exato
    2. Fuzzy match (trata erros de OCR)
    3. Fallback → 3★, sem metadados

    Returns:
        (rarity, nome_canônico, image_url, char_class, attribute, método)
    """
    clean = raw_name.strip().lower()

    def _extract(key: str) -> Tuple[int, str, Optional[str], Optional[str], Optional[str], str]:
        meta = _META_DB.get(key, {})
        return (
            _CHAR_DB[key],
            _CANONICAL[key],
            meta.get("image"),
            meta.get("class"),
            meta.get("attribute"),
            "exact" if key == clean else "fuzzy",
        )

    # 1. Match exato
    if clean in _CHAR_DB:
        meta = _META_DB.get(clean, {})
        return _CHAR_DB[clean], _CANONICAL[clean], meta.get("image"), meta.get("class"), meta.get("attribute"), "exact"

    # 2. Fuzzy match
    matches = difflib.get_close_matches(clean, _KNOWN_NAMES, n=1, cutoff=config.FUZZY_MATCH_CUTOFF)
    if matches:
        best = matches[0]
        score = difflib.SequenceMatcher(None, clean, best).ratio()
        meta = _META_DB.get(best, {})
        return _CHAR_DB[best], _CANONICAL[best], meta.get("image"), meta.get("class"), meta.get("attribute"), f"fuzzy:{score:.2f}"

    # 3. Desconhecido
    return 3, raw_name.strip(), None, None, None, "unknown"


# ──────────────────────────────────────────────────────────────
# Detecção de raridade por cor  (fallback visual — ainda útil
# para novos personagens não cadastrados em characters.json)
# ──────────────────────────────────────────────────────────────

def _color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _detect_rarity_from_color(name_region: np.ndarray) -> int:
    if name_region is None or name_region.size == 0:
        return 3
    hsv = cv2.cvtColor(name_region, cv2.COLOR_BGR2HSV)
    mask = hsv[:, :, 1] > 60
    if mask.sum() < 5:
        return 3
    pixels_bgr = name_region[mask]
    mean_bgr = pixels_bgr.mean(axis=0).astype(int)
    mean_rgb = (int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0]))
    dist_5 = _color_distance(mean_rgb, config.COLOR_5STAR)
    dist_4 = _color_distance(mean_rgb, config.COLOR_4STAR)
    if dist_5 <= config.COLOR_TOLERANCE and dist_5 < dist_4:
        return 5
    if dist_4 <= config.COLOR_TOLERANCE and dist_4 < dist_5:
        return 4
    return 3


# ──────────────────────────────────────────────────────────────
# Estrutura de dados
# ──────────────────────────────────────────────────────────────

@dataclass
class PullEntry:
    name: str
    rarity: int                       # 3, 4 ou 5
    rescue_type: str
    timestamp: str
    raw_row_index: int                # índice dentro da página (0-4)
    image: Optional[str] = None      # URL da imagem (para o frontend)
    char_class: Optional[str] = None # Vanguard, Striker, Ranger, etc.
    attribute: Optional[str] = None  # Order, Justice, Void, Passion, Instinct
    rarity_source: str = "unknown"
    # Preenchidos pelo analyzer:
    pity: int = 0
    pull_number: int = 0
    data_warning: Optional[str] = None  # "pity_exceeds_cap" | None


# ──────────────────────────────────────────────────────────────
# Pré-processamento OCR
# ──────────────────────────────────────────────────────────────

def _preprocess_for_ocr(img_pil: Image.Image) -> Image.Image:
    arr = np.array(img_pil.convert("RGB"))
    h, w = arr.shape[:2]
    arr = cv2.resize(arr, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2,
    )
    return Image.fromarray(binary)


# ──────────────────────────────────────────────────────────────
# Divisão da tabela
# ──────────────────────────────────────────────────────────────

def _split_table_into_rows(table_img: Image.Image, n_rows: int = config.PULLS_PER_PAGE) -> List[Image.Image]:
    w, h = table_img.size
    row_h = h // n_rows
    return [table_img.crop((0, i * row_h, w, (i + 1) * row_h)) for i in range(n_rows)]


def _split_row_into_columns(
    row_img: Image.Image,
    col_ratios: Tuple[float, ...] = config.COL_RATIOS,
) -> List[Image.Image]:
    """Type | Rescue List (nome) | Rescue Type | Rescue Time"""
    w, h = row_img.size
    cols, x = [], 0
    for ratio in col_ratios:
        col_w = int(w * ratio)
        cols.append(row_img.crop((x, 0, x + col_w, h)))
        x += col_w
    return cols


# ──────────────────────────────────────────────────────────────
# OCR de célula
# ──────────────────────────────────────────────────────────────

def _ocr_cell(cell_img: Image.Image) -> str:
    try:
        processed = _preprocess_for_ocr(cell_img)
        text = pytesseract.image_to_string(
            processed,
            lang=config.OCR_LANG,
            config=config.OCR_CONFIG,
        )
        text = re.sub(r"[|\\`~\n\r]", " ", text)
        return " ".join(text.split()).strip()
    except Exception as exc:
        logger.warning("Falha no OCR da célula: %s", exc)
        return ""


# ──────────────────────────────────────────────────────────────
# Processamento de uma página
# ──────────────────────────────────────────────────────────────

def parse_page(table_img: Image.Image, page_number: int = 0) -> List[PullEntry]:
    """
    Processa a imagem da tabela de uma página.

    Lógica de raridade por linha:
    ┌─────────────────────────────────────────────────────────┐
    │ 1. OCR extrai o nome bruto                              │
    │ 2. lookup_rarity() busca no characters.json             │
    │    a. Match exato → raridade confiável                  │
    │    b. Fuzzy match → raridade provável (loga aviso)      │
    │    c. Não encontrado → fallback por cor (loga aviso)    │
    └─────────────────────────────────────────────────────────┘
    """
    entries: List[PullEntry] = []
    rows = _split_table_into_rows(table_img)

    for row_idx, row_img in enumerate(rows):
        try:
            cols = _split_row_into_columns(row_img)
            name_img        = cols[1]
            rescue_type_img = cols[2]
            timestamp_img   = cols[3]

            raw_name    = _ocr_cell(name_img)
            rescue_type = _ocr_cell(rescue_type_img)
            timestamp   = _ocr_cell(timestamp_img)

            if not raw_name:
                logger.debug("Pág %d, linha %d: OCR vazio — pulando.", page_number, row_idx)
                continue

            # ── Lookup completo: raridade, imagem, classe, atributo ──
            rarity, canon_name, image_url, char_class, attribute, method = lookup_character(raw_name)

            if method == "unknown":
                name_arr = cv2.cvtColor(np.array(name_img.convert("RGB")), cv2.COLOR_RGB2BGR)
                rarity_color = _detect_rarity_from_color(name_arr)
                if rarity_color > 3:
                    rarity = rarity_color
                    method = "color"
                    logger.warning(
                        "Pág %d | '%s' não está em characters.json → cor detectou %d★. "
                        "Adicione ao arquivo se necessário.",
                        page_number, raw_name, rarity,
                    )
                else:
                    logger.debug("Pág %d | '%s' não reconhecido → 3★.", page_number, raw_name)
            elif method.startswith("fuzzy"):
                logger.info(
                    "Pág %d | OCR='%s' → fuzzy '%s' (%s) → %d★",
                    page_number, raw_name, canon_name, method, rarity,
                )
            else:
                logger.info(
                    "Pág %d | L%d | '%s' %d★ [%s] | %s | %s",
                    page_number, row_idx, canon_name, rarity, method, rescue_type, timestamp,
                )

            entries.append(PullEntry(
                name=canon_name,
                rarity=rarity,
                rescue_type=rescue_type,
                timestamp=timestamp,
                raw_row_index=row_idx,
                image=image_url,
                char_class=char_class,
                attribute=attribute,
                rarity_source=method,
            ))

        except Exception as exc:
            logger.error("Erro na linha %d da pág %d: %s", row_idx, page_number, exc)

    return entries


# ──────────────────────────────────────────────────────────────
# Filtro
# ──────────────────────────────────────────────────────────────

def filter_notable(entries: List[PullEntry]) -> List[PullEntry]:
    """Retorna apenas pulls 4★ e 5★."""
    return [e for e in entries if e.rarity >= 4]
