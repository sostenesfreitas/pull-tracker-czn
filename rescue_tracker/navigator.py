# navigator.py — Navegação entre páginas do Rescue Records

import ctypes
import ctypes.wintypes
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
# PostMessage click (funciona sem foco, ideal para clientes Electron/web)
# ──────────────────────────────────────────────────────────────

_WM_MOUSEMOVE    = 0x0200
_WM_LBUTTONDOWN  = 0x0201
_WM_LBUTTONUP    = 0x0202
_MK_LBUTTON      = 0x0001


def _find_render_hwnd(parent_hwnd: int) -> int:
    """
    Busca o child window de renderização (Chrome_RenderWidgetHostHWND) dentro do
    parent_hwnd. Se não encontrar, devolve parent_hwnd.
    Necessário para jogos Electron/CEF onde os eventos de mouse são consumidos
    pelo renderer process, não pela janela raiz.
    """
    results: list = []

    EnumChildProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )

    @EnumChildProc
    def _cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
        name = buf.value
        if "Chrome_RenderWidgetHostHWND" in name or "Intermediate D3D Window" in name:
            results.append(hwnd)
        return True

    ctypes.windll.user32.EnumChildWindows(parent_hwnd, _cb, 0)
    return results[-1] if results else parent_hwnd


def _postmessage_click(parent_hwnd: int, screen_x: int, screen_y: int) -> None:
    """
    Envia WM_LBUTTONDOWN / WM_LBUTTONUP diretamente ao handle de renderização
    via PostMessage, convertendo coordenadas de tela → cliente.
    Funciona sem precisar que a janela esteja em foco.
    """
    target = _find_render_hwnd(parent_hwnd)

    pt = ctypes.wintypes.POINT(screen_x, screen_y)
    ctypes.windll.user32.ScreenToClient(target, ctypes.byref(pt))
    lparam = ctypes.c_long((pt.y << 16) | (pt.x & 0xFFFF)).value

    ctypes.windll.user32.PostMessage(target, _WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.03)
    ctypes.windll.user32.PostMessage(target, _WM_LBUTTONDOWN, _MK_LBUTTON, lparam)
    time.sleep(0.08)
    ctypes.windll.user32.PostMessage(target, _WM_LBUTTONUP, 0, lparam)


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
# Foco forçado da janela do jogo
# ──────────────────────────────────────────────────────────────

_VK_MENU = 0x12          # tecla Alt
_KEYEVENTF_KEYUP = 0x02

def _force_game_focus(window: gw.Win32Window) -> None:
    """
    Força a janela do jogo para o primeiro plano usando a API do Windows.

    O "Alt key trick" contorna a restrição do Windows que bloqueia
    SetForegroundWindow() quando o processo chamador não tem o foco.
    Sem isso, pyautogui.click() envia o evento de input mas a janela
    do jogo não o recebe porque não é a janela ativa.
    """
    try:
        hwnd = window._hWnd
        if ctypes.windll.user32.GetForegroundWindow() == hwnd:
            return  # já em foco

        # Pressiona e solta Alt — isso "desbloqueia" SetForegroundWindow
        ctypes.windll.user32.keybd_event(_VK_MENU, 0, 0, 0)
        ctypes.windll.user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        logger.debug("Janela do jogo colocada em foco (hwnd=%s).", hwnd)
    except Exception as exc:
        logger.debug("ctypes SetForegroundWindow falhou (%s); tentando activate().", exc)
        try:
            window.activate()
            time.sleep(0.15)
        except Exception:
            pass


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

    _force_game_focus(window)

    _MOUSEEVENTF_LEFTDOWN = 0x0002
    _MOUSEEVENTF_LEFTUP   = 0x0004

    # Diagnóstico: verifica se rodamos como admin (UIPI bloqueia input se jogo for admin e nós não formos)
    is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    fg_hwnd  = ctypes.windll.user32.GetForegroundWindow()
    logger.info(
        "CLIQUE → alvo=(%d,%d) | admin=%s | foreground_hwnd=%s | game_hwnd=%s",
        click_x, click_y, is_admin, fg_hwnd, window._hWnd,
    )

    # Move cursor e envia mouse_event (API legada)
    ret = ctypes.windll.user32.SetCursorPos(click_x, click_y)
    time.sleep(0.15)

    # Lê posição real após mover para confirmar que SetCursorPos funcionou
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    logger.info("Cursor em (%d, %d) após SetCursorPos (ret=%d)", pt.x, pt.y, ret)

    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.1)
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    logger.info("mouse_event LEFTDOWN+UP enviado")

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
