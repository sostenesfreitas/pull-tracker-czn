# navigator.py — Navegação entre páginas do Rescue Records

import time
import logging
import math
import hashlib
from typing import Tuple, Optional

import pyautogui
import numpy as np
from PIL import Image

import pygetwindow as gw

from . import config
from .capturer import screenshot_next_button, screenshot_table, get_window_rect

logger = logging.getLogger(__name__)

# Tamanho da região capturada ao redor do botão quando usando coord absoluta
_BTN_CAPTURE_RADIUS = 30   # px em cada direção → região 60×60


# ──────────────────────────────────────────────────────────────
# Helpers de cor
# ──────────────────────────────────────────────────────────────

def _color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    """Distância euclidiana entre duas cores RGB."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _dominant_color(img: Image.Image) -> Tuple[int, int, int]:
    """
    Retorna a cor média dos pixels não-pretos da imagem.
    """
    arr = np.array(img.convert("RGB"))
    mask = arr.max(axis=2) > 20        # ignora pixels muito escuros (bordas)
    if mask.sum() == 0:
        return (0, 0, 0)
    pixels = arr[mask]
    mean = pixels.mean(axis=0).astype(int)
    return (int(mean[0]), int(mean[1]), int(mean[2]))


def _judge_button(dominant: Tuple[int, int, int]) -> bool:
    """
    Retorna True se a cor dominante indica botão ATIVO (fundo claro).
    """
    dist_active   = _color_distance(dominant, config.BUTTON_ACTIVE_COLOR)
    dist_inactive = _color_distance(dominant, config.BUTTON_INACTIVE_COLOR)

    logger.debug(
        "Cor dominante do botão=%s | d_ativo=%.1f | d_inativo=%.1f",
        dominant, dist_active, dist_inactive,
    )

    if dist_active <= config.BUTTON_ACTIVE_TOL:
        return True
    if dist_inactive <= config.BUTTON_INACTIVE_TOL:
        return False
    return dist_active < dist_inactive   # desempate


# ──────────────────────────────────────────────────────────────
# Detecção do estado do botão
# (suporta coord absoluta OU relativa à janela)
# ──────────────────────────────────────────────────────────────

def _btn_screen_coords() -> Optional[Tuple[int, int]]:
    """Retorna as coordenadas absolutas de tela do centro do botão '>', ou None."""
    if config.NEXT_BUTTON_SCREEN_COORDS:
        return config.NEXT_BUTTON_SCREEN_COORDS
    return None


def is_next_button_active(window: gw.Win32Window) -> bool:
    """
    Verifica se o botão '>' está ativo (página seguinte disponível).

    Prioridade:
    1. NEXT_BUTTON_SCREEN_COORDS (coord absoluta fornecida pelo usuário via Paint)
    2. NEXT_BUTTON_REGION (coord relativa à janela — fallback)
    """
    try:
        abs_coords = _btn_screen_coords()

        if abs_coords:
            # Captura região ao redor do centro do botão usando coord absoluta
            cx, cy = abs_coords
            r = _BTN_CAPTURE_RADIUS
            region = (cx - r, cy - r, r * 2, r * 2)
            btn_img = pyautogui.screenshot(region=region)
        else:
            btn_img = screenshot_next_button(window)

        dominant = _dominant_color(btn_img)
        return _judge_button(dominant)

    except Exception as exc:
        logger.warning("Erro ao verificar botão de navegação: %s", exc)
        return False   # assume inativo para não entrar em loop infinito


# ──────────────────────────────────────────────────────────────
# Clique no botão de próxima página
# ──────────────────────────────────────────────────────────────

def click_next_button(window: gw.Win32Window) -> None:
    """
    Clica no botão '>'.

    Prioridade:
    1. NEXT_BUTTON_SCREEN_COORDS — clica diretamente nas coords absolutas
    2. NEXT_BUTTON_REGION        — converte relativo→absoluto via posição da janela
    """
    abs_coords = _btn_screen_coords()

    if abs_coords:
        click_x, click_y = abs_coords
        logger.debug("Clicando em '>' (coord absoluta): (%d, %d)", click_x, click_y)
    else:
        x, y, w, h = config.NEXT_BUTTON_REGION
        if w == 0 or h == 0:
            raise RuntimeError(
                "Nem NEXT_BUTTON_SCREEN_COORDS nem NEXT_BUTTON_REGION estão configurados.\n"
                "Execute  python calibrate.py  ou abra config.py e preencha as coords."
            )
        win_x, win_y, _, _ = get_window_rect(window)
        click_x = win_x + x + w // 2
        click_y = win_y + y + h // 2
        logger.debug("Clicando em '>' (relativo à janela): (%d, %d)", click_x, click_y)

    pyautogui.click(click_x, click_y)
    time.sleep(config.DELAY_BETWEEN_PAGES)


# ──────────────────────────────────────────────────────────────
# Iterador de páginas
# ──────────────────────────────────────────────────────────────

def read_page_number(window: gw.Win32Window) -> Optional[int]:
    """
    Lê o número da página atual diretamente da tela via OCR.
    O número fica entre os botões '<' e '>'.
    Retorna None se não conseguir ler.
    """
    try:
        # Região ao redor do número de página (entre os dois botões)
        # Baseado nas coords: botão '>' em x≈1079, botão '<' em x≈795 → centro em x≈937
        cx = (config.NEXT_BUTTON_SCREEN_COORDS[0] + 795) // 2 if config.NEXT_BUTTON_SCREEN_COORDS else None
        if cx is None:
            return None

        cy = config.NEXT_BUTTON_SCREEN_COORDS[1]
        region = (cx - 40, cy - 20, 80, 40)
        img = pyautogui.screenshot(region=region)

        import pytesseract, re
        text = pytesseract.image_to_string(img, config="--psm 7 -c tessedit_char_whitelist=0123456789")
        match = re.search(r"\d+", text)
        if match:
            return int(match.group())
    except Exception:
        pass
    return None


def _table_hash(window: gw.Win32Window) -> str:
    """Hash MD5 do conteúdo atual da tabela."""
    img = screenshot_table(window)
    return hashlib.md5(img.tobytes()).hexdigest()


def _page_counter_hash() -> str:
    """
    Hash MD5 da região do número de página (entre os botões < e >).
    Sempre muda entre páginas diferentes, mesmo quando a tabela tem conteúdo idêntico.
    Região calculada a partir de NEXT_BUTTON_SCREEN_COORDS.
    """
    if not config.NEXT_BUTTON_SCREEN_COORDS:
        return ""
    cx = config.NEXT_BUTTON_SCREEN_COORDS[0] - 140   # ~140 px à esquerda do botão ">"
    cy = config.NEXT_BUTTON_SCREEN_COORDS[1]
    region = (cx - 90, cy - 22, 180, 44)             # cobre o número centralizado
    img = pyautogui.screenshot(region=region)
    return hashlib.md5(img.tobytes()).hexdigest()


def iter_pages(window: gw.Win32Window, max_pages: Optional[int] = None):
    """
    Gerador que itera sobre todas as páginas disponíveis.

    Mecanismos de parada (em ordem de prioridade):
    1. max_pages atingido
    2. Hash da tabela E hash do contador de página inalterados após clique (N vezes)
       — o hash do contador é tiebreaker para páginas com conteúdo visualmente idêntico
    """
    if max_pages is not None:
        logger.info("Limite de páginas: %d", max_pages)

    page = 1
    stuck_count = 0
    MAX_STUCK = 3

    logger.info("Iniciando navegação — página %d", page)
    yield page

    while True:
        # ── 1. Limite manual ──────────────────────────────────
        if max_pages is not None and page >= max_pages:
            logger.info("Limite de %d página(s) atingido. Encerrando.", max_pages)
            break

        # ── 2. Snapshots ANTES do clique ──────────────────────
        table_before   = _table_hash(window)
        counter_before = _page_counter_hash()

        # ── 3. Cor do botão (apenas informativa) ──────────────
        if not is_next_button_active(window):
            logger.debug("Botão '>' aparentemente inativo na página %d — clicando para confirmar.", page)

        # ── 4. Clicar ─────────────────────────────────────────
        try:
            click_next_button(window)
        except Exception as exc:
            logger.error("Erro ao clicar em próxima página: %s", exc)
            break

        # ── 5. Snapshots DEPOIS do clique ─────────────────────
        table_after   = _table_hash(window)
        counter_after = _page_counter_hash()

        table_changed   = table_after   != table_before
        counter_changed = counter_after != counter_before

        if table_changed or counter_changed:
            # Pelo menos um indicador mudou → página avançou
            if not table_changed and counter_changed:
                logger.debug(
                    "Tabela idêntica mas contador mudou (batch com mesmo conteúdo) — continuando."
                )
            stuck_count = 0
            page += 1
            logger.info("Navegando para página %d", page)
            yield page
        else:
            # Nenhum indicador mudou → provavelmente última página
            stuck_count += 1
            logger.warning(
                "Tabela e contador inalterados após clique (tentativa %d/%d).",
                stuck_count, MAX_STUCK,
            )
            if stuck_count >= MAX_STUCK:
                logger.info(
                    "Nenhuma mudança detectada %d vezes → última página atingida (%d).",
                    MAX_STUCK, page,
                )
                break
