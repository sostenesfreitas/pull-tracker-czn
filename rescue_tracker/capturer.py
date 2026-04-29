# capturer.py — Screenshot e controle da janela do jogo (cross-platform: Windows + macOS)

import platform
import subprocess
import time
import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

import pyautogui
from PIL import Image

from . import config

logger = logging.getLogger(__name__)

_OS = platform.system()  # "Windows", "Darwin" (macOS), "Linux"


# ──────────────────────────────────────────────────────────────
# WindowInfo — substitui gw.Win32Window de forma cross-platform
# ──────────────────────────────────────────────────────────────

@dataclass
class WindowInfo:
    """Informações da janela do jogo, independente de plataforma."""
    title: str
    left: int
    top: int
    width: int
    height: int


# ──────────────────────────────────────────────────────────────
# Funções de janela — macOS
# ──────────────────────────────────────────────────────────────

def _find_window_macos(title: str) -> Optional[WindowInfo]:
    """
    Usa osascript para encontrar a janela pelo título e obter sua geometria.
    Retorna separadores claros (pipe) para evitar confusão com vírgulas em nomes.
    """
    # Primeira tentativa: busca pelo nome do processo
    script = f'''
    tell application "System Events"
        set allProcs to every process
        repeat with proc in allProcs
            set procName to name of proc
            if procName contains "{title}" then
                set wins to windows of proc
                if (count of wins) > 0 then
                    set w to item 1 of wins
                    set wPos to position of w
                    set wSize to size of w
                    set x to item 1 of wPos
                    set y to item 2 of wPos
                    set ww to item 1 of wSize
                    set wh to item 2 of wSize
                    return (x as text) & "|" & (y as text) & "|" & (ww as text) & "|" & (wh as text) & "|" & procName
                end if
            end if
        end repeat
    end tell
    return ""
    '''
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True, timeout=8)
    output = result.stdout.strip()

    if output:
        try:
            parts = [p.strip() for p in output.split("|")]
            if len(parts) >= 4:
                x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                win_title = parts[4] if len(parts) > 4 else title
                logger.info("Janela encontrada via osascript: '%s' em (%d,%d) %dx%d",
                            win_title, x, y, w, h)
                return WindowInfo(title=win_title, left=x, top=y, width=w, height=h)
        except (ValueError, IndexError) as exc:
            logger.debug("Falha ao parsear saída do osascript ('%s'): %s", output, exc)

    # Segunda tentativa: janela em foco (frontmost)
    script2 = '''
    tell application "System Events"
        set proc to first process whose frontmost is true
        set wins to windows of proc
        if (count of wins) > 0 then
            set w to item 1 of wins
            set wPos to position of w
            set wSize to size of w
            set x to item 1 of wPos
            set y to item 2 of wPos
            set ww to item 1 of wSize
            set wh to item 2 of wSize
            return (x as text) & "|" & (y as text) & "|" & (ww as text) & "|" & (wh as text) & "|" & (name of proc)
        end if
    end tell
    return ""
    '''
    result2 = subprocess.run(["osascript", "-e", script2],
                             capture_output=True, text=True, timeout=8)
    output2 = result2.stdout.strip()

    if output2:
        try:
            parts = [p.strip() for p in output2.split("|")]
            if len(parts) >= 4:
                x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                proc_name = parts[4] if len(parts) > 4 else "unknown"
                logger.info("Usando janela em foco: '%s' em (%d,%d) %dx%d", proc_name, x, y, w, h)
                return WindowInfo(title=proc_name, left=x, top=y, width=w, height=h)
        except (ValueError, IndexError) as exc:
            logger.debug("Falha ao parsear janela em foco ('%s'): %s", output2, exc)

    return None


def _focus_window_macos(title: str) -> bool:
    """Ativa a janela do jogo no macOS via osascript."""
    script = f'''
    tell application "System Events"
        set appList to every process whose name contains "{title}"
        if appList is not {{}} then
            set frontmost of (item 1 of appList) to true
            return "ok"
        end if
    end tell
    return "not found"
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        return "ok" in result.stdout
    except Exception as exc:
        logger.warning("Erro ao focar janela via osascript: %s", exc)
        return False


# ──────────────────────────────────────────────────────────────
# Funções de janela — Windows
# ──────────────────────────────────────────────────────────────

def _find_window_windows(title: str) -> Optional[WindowInfo]:
    """Usa pygetwindow para encontrar a janela no Windows."""
    try:
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(title)
        if not windows:
            return None
        w = windows[0]
        return WindowInfo(title=w.title, left=w.left, top=w.top, width=w.width, height=w.height)
    except Exception as exc:
        logger.warning("Erro ao buscar janela (Windows): %s", exc)
        return None


def _focus_window_windows(window: WindowInfo) -> bool:
    """Foca a janela no Windows via pygetwindow."""
    try:
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(window.title)
        if not windows:
            return False
        w = windows[0]
        if w.isMinimized:
            w.restore()
        w.activate()
        return True
    except Exception as exc:
        logger.warning("Erro ao focar janela (Windows): %s", exc)
        return False


# ──────────────────────────────────────────────────────────────
# API pública de janela (cross-platform)
# ──────────────────────────────────────────────────────────────

def find_game_window() -> Optional[WindowInfo]:
    """
    Procura a janela do jogo pelo título configurado (cross-platform).

    Se a janela não for encontrada MAS TABLE_SCREEN_REGION e
    NEXT_BUTTON_SCREEN_COORDS já estiverem configurados (coordenadas absolutas),
    retorna uma WindowInfo virtual — o tracker funciona normalmente porque
    não precisa das coordenadas relativas da janela.
    """
    title = config.WINDOW_TITLE

    if _OS == "Darwin":
        window = _find_window_macos(title)
    elif _OS == "Windows":
        window = _find_window_windows(title)
    else:
        window = None

    if window is not None:
        logger.info("Janela encontrada: '%s' em (%d, %d) tamanho %dx%d",
                    window.title, window.left, window.top, window.width, window.height)
        return window

    # Janela não encontrada — verifica se as coords absolutas estão configuradas
    coords_ok = (
        config.TABLE_SCREEN_REGION and
        config.NEXT_BUTTON_SCREEN_COORDS
    )

    if coords_ok:
        logger.warning(
            "Janela '%s' não encontrada via detecção automática, mas "
            "TABLE_SCREEN_REGION e NEXT_BUTTON_SCREEN_COORDS estão configurados. "
            "Continuando no modo de coordenadas absolutas — "
            "certifique-se de que o jogo está aberto e visível na tela.",
            title
        )
        # Estima posição/tamanho a partir da região da tabela configurada
        tx, ty, tw, th = config.TABLE_SCREEN_REGION
        return WindowInfo(title=title, left=tx, top=ty, width=tw + 200, height=th + 400)

    logger.error(
        "Janela '%s' não encontrada. Certifique-se de que o jogo está aberto.\n"
        "Se o problema persistir, rode primeiro: python3 calibrar.py",
        title
    )
    return None


def focus_game_window(window: WindowInfo) -> bool:
    """Traz a janela do jogo para o foco (cross-platform)."""
    try:
        if _OS == "Darwin":
            ok = _focus_window_macos(window.title)
        elif _OS == "Windows":
            ok = _focus_window_windows(window)
        else:
            ok = False

        if ok:
            time.sleep(config.DELAY_AFTER_FOCUS)
            logger.debug("Janela focada com sucesso.")
        else:
            logger.warning("Não foi possível focar a janela automaticamente.")
        return ok
    except Exception as exc:
        logger.warning("Erro ao focar janela: %s", exc)
        return False


def get_window_rect(window: WindowInfo) -> Tuple[int, int, int, int]:
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

    No macOS usa screencapture diretamente para evitar problemas com
    pyscreeze/pyautogui. Requer permissão de Gravação de Tela:
        Configurações → Privacidade → Gravação de Tela → Terminal (ON)
    """
    x, y, w, h = region

    if _OS == "Darwin":
        return _screenshot_region_mac(x, y, w, h)

    img = pyautogui.screenshot(region=(x, y, w, h))
    return img


def _screenshot_region_mac(x: int, y: int, w: int, h: int) -> Image.Image:
    """Captura região via screencapture (macOS). Lança erro claro se sem permissão."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        # -R x,y,w,h  — região em pontos lógicos (não físicos)
        # -x           — sem som de câmera
        result = subprocess.run(
            ["screencapture", "-R", f"{int(x)},{int(y)},{int(w)},{int(h)}", "-x", tmp_path],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="ignore").strip()
            if "intersect" in stderr or not os.path.exists(tmp_path):
                raise RuntimeError(
                    f"Região ({x},{y},{w},{h}) está fora dos limites da tela.\n"
                    "Execute  python3 calibrar.py  para reconfigurar as coordenadas."
                )
            raise RuntimeError(
                f"screencapture falhou (código {result.returncode}).\n"
                "Verifique: Configurações → Privacidade → Gravação de Tela → Terminal (ON)"
            )
        return Image.open(tmp_path).copy()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def screenshot_full_window(window: WindowInfo) -> Image.Image:
    """Captura a janela inteira do jogo."""
    region = get_window_rect(window)
    return screenshot_region(region)


def screenshot_table(window: WindowInfo) -> Image.Image:
    """
    Captura apenas a região da tabela de pulls.

    Prioridade:
    1. TABLE_SCREEN_REGION — coordenadas absolutas (definidas pelo calibrar.py)
    2. TABLE_REGION        — coordenadas relativas à janela
    3. Janela inteira       — fallback
    """
    if config.TABLE_SCREEN_REGION:
        logger.debug("Capturando tabela por coord absoluta: %s", config.TABLE_SCREEN_REGION)
        return screenshot_region(config.TABLE_SCREEN_REGION)

    x, y, w, h = config.TABLE_REGION
    if w != 0 and h != 0:
        win_x, win_y, _, _ = get_window_rect(window)
        abs_region = (win_x + x, win_y + y, w, h)
        return screenshot_region(abs_region)

    logger.warning(
        "TABLE_SCREEN_REGION não configurado — capturando janela completa. "
        "Execute: python calibrar.py"
    )
    return screenshot_full_window(window)


def screenshot_next_button(window: WindowInfo) -> Image.Image:
    """Captura a região do botão '>' de próxima página."""
    x, y, w, h = config.NEXT_BUTTON_REGION
    if w == 0 or h == 0:
        logger.warning("NEXT_BUTTON_REGION não configurado.")
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
