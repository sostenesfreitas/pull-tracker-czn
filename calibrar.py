#!/usr/bin/env python3
"""
calibrar.py — Ferramenta visual de calibração de regiões (macOS + Windows)

Como usar:
    1. Abra o jogo na tela de Rescue Records
    2. Execute: python calibrar.py
    3. Siga as instruções na tela:
         - Arraste para selecionar a TABELA de pulls
         - Clique no centro do BOTÃO ">" de próxima página
    4. As coordenadas são salvas automaticamente no config.py
"""

import sys
import os
import re
import time
import platform
import subprocess
import tempfile
import tkinter as tk
from tkinter import messagebox, filedialog, font as tkfont
from PIL import Image, ImageTk
import pyautogui

_OS = platform.system()

# ──────────────────────────────────────────────────────────────
# Captura de tela completa
# ──────────────────────────────────────────────────────────────

def _capturar_via_screencapture() -> Image.Image:
    """Usa screencapture diretamente (macOS) — requer permissão de Gravação de Tela."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        # -x = sem som; sem -i = captura toda a tela
        result = subprocess.run(
            ["screencapture", "-x", tmp_path],
            capture_output=True, timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(f"screencapture retornou código {result.returncode}")
        return Image.open(tmp_path).copy()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _pedir_screenshot_manual() -> Image.Image:
    """
    Fallback: pede ao usuário para tirar um screenshot manualmente
    e selecionar o arquivo PNG resultante.
    """
    print()
    print("┌─────────────────────────────────────────────────────┐")
    print("│  Permissão de Gravação de Tela necessária           │")
    print("│                                                     │")
    print("│  OPÇÃO 1 — Conceder permissão (recomendado):        │")
    print("│    1. Abra: Configurações → Privacidade →           │")
    print("│            Gravação de Tela                         │")
    print("│    2. Adicione e habilite o Terminal / Python       │")
    print("│    3. Rode novamente: python3 calibrar.py           │")
    print("│                                                     │")
    print("│  OPÇÃO 2 — Usar screenshot manual (agora):          │")
    print("│    1. Abra o jogo na tela de Rescue Records         │")
    print("│    2. Pressione Cmd+Shift+3 para capturar a tela    │")
    print("│    3. O arquivo PNG é salvo na Área de Trabalho     │")
    print("│    4. Selecione o arquivo quando solicitado abaixo  │")
    print("└─────────────────────────────────────────────────────┘")
    print()

    # Abre as configurações de permissão automaticamente
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"],
        capture_output=True
    )

    opcao = input("Escolha — (1) Sair e configurar permissão  (2) Selecionar PNG manualmente: ").strip()
    if opcao != "2":
        print()
        print("Após conceder a permissão, rode: python3 calibrar.py")
        sys.exit(0)

    # Tkinter para abrir o seletor de arquivo
    root = tk.Tk()
    root.withdraw()
    caminho = filedialog.askopenfilename(
        title="Selecione o screenshot da tela de Rescue Records",
        filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp"), ("Todos", "*.*")],
        initialdir=os.path.expanduser("~/Desktop"),
    )
    root.destroy()

    if not caminho:
        print("Nenhum arquivo selecionado. Encerrando.")
        sys.exit(1)

    print(f"Usando: {caminho}")
    return Image.open(caminho)


def capturar_tela() -> Image.Image:
    """
    Captura a tela inteira.
    No macOS requer permissão de Gravação de Tela.
    Se falhar, oferece fallback para selecionar um PNG manualmente.
    """
    try:
        if _OS == "Darwin":
            return _capturar_via_screencapture()
        else:
            return pyautogui.screenshot()
    except Exception as exc:
        # Permissão negada ou outro erro de captura
        if _OS == "Darwin" and ("non-zero" in str(exc) or "screencapture" in str(exc).lower()
                                 or "display" in str(exc).lower()):
            return _pedir_screenshot_manual()
        raise


# ──────────────────────────────────────────────────────────────
# Salvar no config.py
# ──────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "rescue_tracker", "config.py")


def _patch_config(key: str, value: str) -> None:
    """Substitui o valor de uma chave no config.py."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Padrão: KEY = (qualquer coisa até fim de linha)
    pattern = rf"^({re.escape(key)}\s*=\s*)(.+)$"
    replacement = rf"\g<1>{value}"
    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if new_content == content:
        print(f"[AVISO] Chave '{key}' não encontrada no config.py — adicionando ao final.")
        new_content += f"\n{key} = {value}\n"

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  config.py → {key} = {value}")


def salvar_coordenadas(table_region, button_coords):
    """Salva TABLE_SCREEN_REGION e NEXT_BUTTON_SCREEN_COORDS no config.py."""
    _patch_config("TABLE_SCREEN_REGION", str(table_region))
    _patch_config("NEXT_BUTTON_SCREEN_COORDS", str(button_coords))
    print("\n[OK] Coordenadas salvas em rescue_tracker/config.py")


# ──────────────────────────────────────────────────────────────
# Interface Tkinter — overlay de calibração
# ──────────────────────────────────────────────────────────────

class Calibrador:
    PHASE_TABLE  = "table"
    PHASE_BUTTON = "button"
    PHASE_DONE   = "done"

    # Cores de destaque
    COR_TABELA  = "#00E5FF"   # ciano
    COR_BOTAO   = "#FF4081"   # rosa
    COR_OVERLAY = "#0D1117"   # fundo escuro semitransparente (simulado)

    def __init__(self, screenshot: Image.Image):
        self.screenshot = screenshot
        self.screen_w, self.screen_h = screenshot.size

        # Coordenadas resultado
        self.table_region   = None   # (x, y, w, h) em pontos lógicos (para screencapture)
        self.button_coords  = None   # (cx, cy)   em pontos lógicos

        # Estado de arraste
        self._drag_start = None
        self._drag_rect_id = None

        # ── Fator Retina (HiDPI) ──────────────────────────────
        # screencapture -R usa pontos lógicos (1x), mas o screenshot
        # capturado pela screencapture -x é em pixels físicos (2x em Retina).
        # Detectamos o fator comparando o tamanho do screenshot com
        # o tamanho lógico da tela reportado pelo Tk.
        root_tmp = tk.Tk()
        root_tmp.withdraw()
        logical_w = root_tmp.winfo_screenwidth()
        logical_h = root_tmp.winfo_screenheight()
        root_tmp.destroy()
        self._retina = self.screen_w / logical_w   # e.g. 2.0 em Retina, 1.0 em não-Retina
        self._logical_w = logical_w
        self._logical_h = logical_h

        # Escala para caber na janela (canvas menor que o screenshot)
        self._scale = 1.0

        self._phase = self.PHASE_TABLE
        self._build_ui()

    # ── Construção da UI ─────────────────────────────────────

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("Pull Tracker — Calibração")
        self.root.configure(bg=self.COR_OVERLAY)
        self.root.resizable(False, False)

        # ── Painel de instrução (topo) ─────────────────────
        top = tk.Frame(self.root, bg="#161B22", pady=8)
        top.pack(fill=tk.X)

        self.lbl_fase = tk.Label(
            top, text="", font=("Helvetica", 15, "bold"),
            bg="#161B22", fg="#FFFFFF", padx=16,
        )
        self.lbl_fase.pack(side=tk.LEFT)

        self.lbl_instrucao = tk.Label(
            top, text="", font=("Helvetica", 12),
            bg="#161B22", fg="#AAAAAA", padx=8,
        )
        self.lbl_instrucao.pack(side=tk.LEFT)

        # ── Canvas com screenshot ──────────────────────────
        # Redimensiona para caber na tela lógica (tkinter usa pontos lógicos)
        max_w = min(self._logical_w - 40, 1440)
        max_h = min(self._logical_h - 120, 900)
        self._scale = min(max_w / self.screen_w, max_h / self.screen_h, 1.0)

        canvas_w = int(self.screen_w * self._scale)
        canvas_h = int(self.screen_h * self._scale)

        self.canvas = tk.Canvas(
            self.root, width=canvas_w, height=canvas_h,
            cursor="crosshair", bg="#000000",
            highlightthickness=0,
        )
        self.canvas.pack()

        # Exibe screenshot escalado
        img_resized = self.screenshot.resize((canvas_w, canvas_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(img_resized)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._tk_img)

        # ── Painel inferior ────────────────────────────────
        bottom = tk.Frame(self.root, bg="#161B22", pady=6)
        bottom.pack(fill=tk.X)

        self.lbl_coords = tk.Label(
            bottom, text="Coordenadas: —",
            font=("Courier", 11), bg="#161B22", fg="#58A6FF", padx=16,
        )
        self.lbl_coords.pack(side=tk.LEFT)

        self.btn_refazer = tk.Button(
            bottom, text="↩  Refazer", font=("Helvetica", 11),
            bg="#21262D", fg="#FFFFFF", relief=tk.FLAT, padx=12, pady=4,
            command=self._refazer,
        )
        self.btn_refazer.pack(side=tk.RIGHT, padx=8)
        self.btn_refazer.config(state=tk.DISABLED)

        # ── Eventos do mouse ───────────────────────────────
        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>",          self._on_move)

        self._atualizar_instrucao()

    # ── Lógica de fases ──────────────────────────────────────

    def _atualizar_instrucao(self):
        if self._phase == self.PHASE_TABLE:
            self.lbl_fase.config(text="PASSO 1 / 2 — Tabela de pulls", fg=self.COR_TABELA)
            self.lbl_instrucao.config(
                text="Arraste para selecionar as 5 linhas da tabela  (do topo ao fim da última linha)"
            )
        elif self._phase == self.PHASE_BUTTON:
            self.lbl_fase.config(text="PASSO 2 / 2 — Botão  >", fg=self.COR_BOTAO)
            self.lbl_instrucao.config(
                text="Clique no centro do botão  >  (próxima página)"
            )
        elif self._phase == self.PHASE_DONE:
            self.lbl_fase.config(text="Calibração concluída!", fg="#3FB950")
            self.lbl_instrucao.config(text="Coordenadas salvas em config.py. Pode fechar.")

    # ── Eventos mouse ────────────────────────────────────────

    def _canvas_to_real(self, cx, cy):
        """
        Converte coordenada do canvas para pontos lógicos de tela.

        Pipeline:
          canvas px  →  (÷ canvas_scale)  →  screenshot px (físico)
                     →  (÷ retina_factor) →  pontos lógicos (screencapture)
        """
        total_scale = self._scale * self._retina
        return int(cx / total_scale), int(cy / total_scale)

    def _on_move(self, event):
        rx, ry = self._canvas_to_real(event.x, event.y)
        self.lbl_coords.config(text=f"x={rx}  y={ry}")

    def _on_press(self, event):
        if self._phase == self.PHASE_TABLE:
            self._drag_start = (event.x, event.y)
            if self._drag_rect_id:
                self.canvas.delete(self._drag_rect_id)

        elif self._phase == self.PHASE_BUTTON:
            # Clique simples → salva coords do botão
            rx, ry = self._canvas_to_real(event.x, event.y)
            self.button_coords = (rx, ry)

            # Marca com círculo
            r = int(20 * self._scale)
            self.canvas.create_oval(
                event.x - r, event.y - r,
                event.x + r, event.y + r,
                outline=self.COR_BOTAO, width=3, tags="btn_mark"
            )
            self.canvas.create_line(
                event.x - r, event.y, event.x + r, event.y,
                fill=self.COR_BOTAO, width=2, tags="btn_mark"
            )
            self.canvas.create_line(
                event.x, event.y - r, event.x, event.y + r,
                fill=self.COR_BOTAO, width=2, tags="btn_mark"
            )
            self.lbl_coords.config(
                text=f"Botão: ({rx}, {ry})  ✓  —  Feche e rode  python run.py"
            )
            self._fase_concluida()

    def _on_drag(self, event):
        if self._phase != self.PHASE_TABLE or not self._drag_start:
            return
        x0, y0 = self._drag_start
        if self._drag_rect_id:
            self.canvas.coords(self._drag_rect_id, x0, y0, event.x, event.y)
        else:
            self._drag_rect_id = self.canvas.create_rectangle(
                x0, y0, event.x, event.y,
                outline=self.COR_TABELA, width=2, fill="", dash=(6, 3),
            )

    def _on_release(self, event):
        if self._phase != self.PHASE_TABLE or not self._drag_start:
            return

        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y

        # Garante x0 < x1 e y0 < y1
        if x0 > x1: x0, x1 = x1, x0
        if y0 > y1: y0, y1 = y1, y0

        # Descarta seleções minúsculas (< 20px)
        if abs(x1 - x0) < 20 or abs(y1 - y0) < 20:
            return

        # Converte para coords reais
        rx0, ry0 = self._canvas_to_real(x0, y0)
        rx1, ry1 = self._canvas_to_real(x1, y1)
        rw = rx1 - rx0
        rh = ry1 - ry0
        self.table_region = (rx0, ry0, rw, rh)

        # Redesenha retângulo sólido confirmado
        if self._drag_rect_id:
            self.canvas.delete(self._drag_rect_id)
        self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline=self.COR_TABELA, width=3, fill="", tags="table_rect"
        )
        # Label com medidas
        self.canvas.create_text(
            x0 + 6, y0 - 10,
            text=f"({rx0}, {ry0})  {rw}×{rh}px",
            fill=self.COR_TABELA, anchor=tk.W,
            font=("Courier", 10, "bold"), tags="table_rect",
        )

        self.lbl_coords.config(
            text=f"Tabela: ({rx0}, {ry0}, {rw}, {rh})  ✓"
        )
        self.btn_refazer.config(state=tk.NORMAL)

        # Avança para fase do botão
        self._phase = self.PHASE_BUTTON
        self._atualizar_instrucao()
        self._drag_start = None

    # ── Ações ────────────────────────────────────────────────

    def _refazer(self):
        """Volta para o início da calibração."""
        self.table_region  = None
        self.button_coords = None
        self.canvas.delete("table_rect")
        self.canvas.delete("btn_mark")
        self._drag_start   = None
        self._drag_rect_id = None
        self._phase = self.PHASE_TABLE
        self._atualizar_instrucao()
        self.lbl_coords.config(text="Coordenadas: —")
        self.btn_refazer.config(state=tk.DISABLED)

    def _fase_concluida(self):
        """Chamada quando botão é marcado — salva e exibe resultado."""
        self._phase = self.PHASE_DONE
        self._atualizar_instrucao()
        self.btn_refazer.config(state=tk.NORMAL)

        salvar_coordenadas(self.table_region, self.button_coords)

        messagebox.showinfo(
            "Calibração concluída!",
            f"Coordenadas salvas em rescue_tracker/config.py\n\n"
            f"Tabela  : {self.table_region}\n"
            f"Botão > : {self.button_coords}\n\n"
            f"Agora execute:\n    python run.py",
        )

    # ── Loop principal ───────────────────────────────────────

    def run(self):
        self.root.mainloop()


# ──────────────────────────────────────────────────────────────
# Ponto de entrada
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Pull Tracker — Calibração Visual")
    print("=" * 60)
    print()
    print("Capturando a tela...")
    print("(Se o jogo não estiver visível, minimize esta janela do terminal")
    print(" e abra o jogo na tela de Rescue Records antes de continuar.)")
    print()

    # Pequena pausa para o usuário posicionar o jogo
    for i in range(3, 0, -1):
        print(f"  Capturando em {i}s...", end="\r")
        time.sleep(1)
    print()

    screenshot = capturar_tela()
    phys_w, phys_h = screenshot.size

    # Detecta escala Retina para exibir ao usuário
    root_tmp = tk.Tk(); root_tmp.withdraw()
    log_w = root_tmp.winfo_screenwidth()
    log_h = root_tmp.winfo_screenheight()
    root_tmp.destroy()
    retina = phys_w / log_w

    print(f"Tela capturada: {phys_w}×{phys_h}px (físico)")
    print(f"Tela lógica:    {log_w}×{log_h}pt  (screencapture usa pontos lógicos)")
    if retina > 1.1:
        print(f"Display Retina detectado — fator {retina:.1f}x (compensação automática ativa)")
    else:
        print(f"Display padrão (1x)")
    print()
    print("Instruções:")
    print("  1. Arraste para selecionar a tabela de pulls")
    print("  2. Clique no centro do botão '>' de próxima página")
    print("  3. As coordenadas serão salvas automaticamente")
    print()

    app = Calibrador(screenshot)
    app.run()


if __name__ == "__main__":
    main()
