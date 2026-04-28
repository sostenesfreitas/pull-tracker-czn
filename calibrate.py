#!/usr/bin/env python3
"""
Ferramenta de calibração — ajuda a descobrir as coordenadas corretas
para TABLE_REGION e NEXT_BUTTON_REGION no config.py.

Uso:
    python calibrate.py

Instruções:
1. Execute este script enquanto o jogo está aberto na tela de Rescue Records.
2. O script abre uma janela mostrando a captura da janela do jogo.
3. Use o mouse para selecionar as regiões desejadas.
4. As coordenadas são impressas no terminal para copiar no config.py.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import cv2
import numpy as np
import pygetwindow as gw
import pyautogui
from PIL import Image

from rescue_tracker import config


# ──────────────────────────────────────────────────────────────
# Captura
# ──────────────────────────────────────────────────────────────

def capture_window_screenshot():
    windows = gw.getWindowsWithTitle(config.WINDOW_TITLE)
    if not windows:
        print(f"[ERRO] Janela '{config.WINDOW_TITLE}' não encontrada.")
        print("Abra o jogo e execute novamente.")
        sys.exit(1)
    win = windows[0]
    win.activate()
    import time; time.sleep(0.5)
    img_pil = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
    return img_pil, (win.left, win.top)


# ──────────────────────────────────────────────────────────────
# Seleção interativa com OpenCV
# ──────────────────────────────────────────────────────────────

def select_region(img_cv, window_name: str, label: str):
    """
    Abre uma janela OpenCV e deixa o usuário arrastar para selecionar uma região.
    Retorna (x, y, w, h) relativo à imagem.
    """
    print(f"\n{'='*50}")
    print(f"Selecione: {label}")
    print("→ Arraste o mouse para desenhar o retângulo.")
    print("→ Pressione ENTER ou ESPAÇO para confirmar.")
    print("→ Pressione C para cancelar/redesenhar.")
    print(f"{'='*50}")

    roi = cv2.selectROI(window_name, img_cv, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(window_name)

    x, y, w, h = [int(v) for v in roi]
    print(f"  Região selecionada: x={x}, y={y}, largura={w}, altura={h}")
    return x, y, w, h


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Pull Tracker — Calibração de Regiões")
    print("=" * 60)

    img_pil, (win_x, win_y) = capture_window_screenshot()
    img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    # Redimensiona para caber na tela (máx 1280px de largura)
    h, w = img_cv.shape[:2]
    scale = 1.0
    if w > 1280:
        scale = 1280 / w
        img_cv_display = cv2.resize(img_cv, (int(w * scale), int(h * scale)))
    else:
        img_cv_display = img_cv.copy()

    # ── Tabela ──
    tx, ty, tw, th = select_region(img_cv_display.copy(), "Selecione TABLE_REGION", "Tabela de pulls (5 linhas)")
    # Ajusta escala de volta
    tx = int(tx / scale); ty = int(ty / scale)
    tw = int(tw / scale); th = int(th / scale)

    # ── Botão ──
    bx, by, bw, bh = select_region(img_cv_display.copy(), "Selecione NEXT_BUTTON_REGION", "Botão '>' (próxima página)")
    bx = int(bx / scale); by = int(by / scale)
    bw = int(bw / scale); bh = int(bh / scale)

    # ── Resultado ──
    print("\n" + "=" * 60)
    print("Copie as linhas abaixo para o arquivo  rescue_tracker/config.py:")
    print("=" * 60)
    print(f"TABLE_REGION       = ({tx}, {ty}, {tw}, {th})")
    print(f"NEXT_BUTTON_REGION = ({bx}, {by}, {bw}, {bh})")
    print("=" * 60)

    # Preview com retângulos desenhados
    preview = img_cv.copy()
    cv2.rectangle(preview, (tx, ty), (tx + tw, ty + th), (0, 255, 0), 2)
    cv2.rectangle(preview, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
    cv2.putText(preview, "Tabela",  (tx, ty - 8),  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(preview, "Botao >", (bx, by - 8),  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    if w > 1280:
        preview = cv2.resize(preview, (int(w * scale), int(h * scale)))

    cv2.imshow("Calibracao — Pressione qualquer tecla para fechar", preview)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
