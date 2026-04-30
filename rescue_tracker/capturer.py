# capturer.py — Screenshot e controle da janela do jogo

import ctypes
import time
import logging
import os
from typing import Optional, Tuple

import pyautogui
import pygetwindow as gw
from PIL import Image

from . import config

logger = logging.getLogger(__name__)

_VK_MENU = 0x12
_KEYEVENTF_KEYUP = 0x02


# ──────────────────────────────────────────────────────────────
# Funções de janela
# ──────────────────────────────────────────────────────────────

def find_game_window() -> Optional[gw.Win32Window]:
    """Procura a janela do jogo pelo título configurado."""
    windows = gw.getWindowsWithTitle(config.WINDOW_TITLE)
    # Exclui a própria janela do Pull Tracker (título começa com "Pull Tracker")
    # para evitar match falso quando WINDOW_TITLE é substring do título da GUI.
    windows = [w for w in windows if not w.title.startswith("Pull Tracker")]
    if not windows:
        logger.error("Janela '%s' não encontrada. Certifique-se de que o jogo está aberto.", config.WINDOW_TITLE)
        return None
    logger.info("Janela encontrada: '%s'", windows[0].title)
    return windows[0]


def focus_game_window(window: gw.Win32Window) -> bool:
    """
    Traz a janela do jogo para o primeiro plano usando ctypes.

    Usa o 'Alt key trick' para contornar a restrição do Windows que
    impede SetForegroundWindow() de funcionar a partir de processos
    que não têm o foco no momento da chamada.
    """
    try:
        if window.isMinimized:
            window.restore()
            time.sleep(0.2)

        hwnd = window._hWnd
        # Pressiona e solta Alt para desbloquear SetForegroundWindow
        ctypes.windll.user32.keybd_event(_VK_MENU, 0, 0, 0)
        ctypes.windll.user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.SetForegroundWindow(hwnd)

        time.sleep(config.DELAY_AFTER_FOCUS)
        logger.debug("Janela focada com sucesso (hwnd=%s).", hwnd)
        return True
    except Exception as exc:
        logger.warning("Não foi possível focar a janela via ctypes (%s); tentando activate().", exc)
        try:
            window.activate()
            time.sleep(config.DELAY_AFTER_FOCUS)
            return True
        except Exception:
            return False


def get_window_rect(window: gw.Win32Window) -> Tuple[int, int, int, int]:
    """Retorna (x, y, largura, altura) da janela."""
    return window.left, window.top, window.width, window.height


# ──────────────────────────────────────────────────────────────
# Funções de captura
# ──────────────────────────────────────────────────────────────

def screenshot_region(region: Tuple[int, int, int, int]) -> Image.Image:
    """
    Captura uma região da tela.

    Args:
        region: (x, y, largura, altura) em coordenadas absolutas de tela.

    Returns:
        Imagem PIL da região.
    """
    x, y, w, h = region
    img = pyautogui.screenshot(region=(x, y, w, h))
    return img


def screenshot_full_window(window: gw.Win32Window) -> Image.Image:
    """Captura a janela inteira do jogo."""
    region = get_window_rect(window)
    return screenshot_region(region)


def screenshot_table(window: gw.Win32Window) -> Image.Image:
    """
    Captura apenas a região da tabela de pulls.

    Prioridade:
    1. TABLE_SCREEN_REGION — coordenadas absolutas de tela (fornecidas pelo usuário via Paint)
    2. TABLE_REGION        — coordenadas relativas à janela
    3. Janela inteira       — fallback se nada estiver configurado
    """
    # 1. Coordenada absoluta
    if config.TABLE_SCREEN_REGION:
        logger.debug("Capturando tabela por coord absoluta: %s", config.TABLE_SCREEN_REGION)
        return screenshot_region(config.TABLE_SCREEN_REGION)

    # 2. Coordenada relativa à janela
    x, y, w, h = config.TABLE_REGION
    if w != 0 and h != 0:
        win_x, win_y, _, _ = get_window_rect(window)
        abs_region = (win_x + x, win_y + y, w, h)
        return screenshot_region(abs_region)

    # 3. Fallback — janela completa
    logger.warning(
        "TABLE_SCREEN_REGION e TABLE_REGION não configurados — "
        "capturando janela completa. Execute python calibrate.py."
    )
    return screenshot_full_window(window)


def screenshot_next_button(window: gw.Win32Window) -> Image.Image:
    """Captura a região do botão '>' de próxima página."""
    x, y, w, h = config.NEXT_BUTTON_REGION
    if w == 0 or h == 0:
        logger.warning("NEXT_BUTTON_REGION não configurado.")
        # Retorna imagem vazia 1×1 para não quebrar o fluxo
        return Image.new("RGB", (1, 1), (0, 0, 0))

    win_x, win_y, _, _ = get_window_rect(window)
    abs_region = (win_x + x, win_y + y, w, h)
    return screenshot_region(abs_region)


# ──────────────────────────────────────────────────────────────
# Utilitários de debug
# ──────────────────────────────────────────────────────────────

def save_debug_screenshot(img: Image.Image, page_number: int) -> None:
    """Salva screenshot de debug se DEBUG_SAVE_SCREENSHOTS estiver ativado."""
    if not config.DEBUG_SAVE_SCREENSHOTS:
        return
    os.makedirs(config.DEBUG_DIR, exist_ok=True)
    path = os.path.join(config.DEBUG_DIR, f"page_{page_number:04d}.png")
    img.save(path)
    logger.debug("Screenshot de debug salvo: %s", path)
