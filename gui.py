"""gui.py — Pull Tracker GUI (Chaos Zero Nightmare)"""

import sys
import os
import re
import time
import threading
import queue
import logging
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
import pyautogui
import pygetwindow as gw
from PIL import Image, ImageTk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _base_dir() -> str:
    """Diretório gravável: próximo ao .exe (frozen) ou ao gui.py (source)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _calib_json_path() -> str:
    return os.path.join(_base_dir(), "calibration.json")


def _load_calibration() -> None:
    """Carrega calibration.json e aplica no módulo config em memória."""
    path = _calib_json_path()
    if not os.path.exists(path):
        return
    try:
        import json
        from rescue_tracker import config as cfg
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "TABLE_SCREEN_REGION" in data:
            cfg.TABLE_SCREEN_REGION = tuple(data["TABLE_SCREEN_REGION"])
        if "NEXT_BUTTON_SCREEN_COORDS" in data:
            cfg.NEXT_BUTTON_SCREEN_COORDS = tuple(data["NEXT_BUTTON_SCREEN_COORDS"])
    except Exception:
        pass

_PURPLE      = "#9B59B6"
_PURPLE_DARK = "#7D3C98"
_RED         = "#C0392B"
_RED_DARK    = "#922B21"
_GREEN       = "#27AE60"
_ORANGE      = "#E67E22"
_BG_HEADER   = "#16213E"


# ── Thread-safe log handler ────────────────────────────────────────────────────

class _QueueHandler(logging.Handler):
    def __init__(self, q: "queue.Queue[str]"):
        super().__init__()
        self.q = q
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        )

    def emit(self, record: logging.LogRecord):
        self.q.put(self.format(record))


# ── Calibration window ─────────────────────────────────────────────────────────

class CalibrateWindow(ctk.CTkToplevel):
    """
    Modal visual calibration.
    Step 1 — drag to select the 5 data rows (TABLE_SCREEN_REGION).
    Step 2 — click center of '>' button (NEXT_BUTTON_SCREEN_COORDS).
    """

    _STEPS = {
        "table": (
            "Passo 1 de 2  —  Área da tabela",
            "Arraste sobre as 5 linhas de dados (sem o cabeçalho Type / Rescue List / ...).",
            "#F39C12", "#2d1f00",
        ),
        "button": (
            "Passo 2 de 2  —  Botão '>' (próxima página)",
            "Clique no centro do botão '>' para registrar as coordenadas de clique.",
            "#3498DB", "#001f3f",
        ),
        "done": (
            "✓  Calibração concluída",
            "Ambas as regiões detectadas. Clique em 'Salvar e Fechar' para aplicar.",
            "#2ECC71", "#0d2a14",
        ),
    }

    def __init__(self, parent, on_saved=None):
        super().__init__(parent)
        self.title("Calibrar Regiões — Pull Tracker")
        self.grab_set()
        self.resizable(True, True)

        self._parent     = parent
        self._on_saved   = on_saved
        self._win_x      = 0
        self._win_y      = 0
        self._scale      = 1.0
        self._step       = "table"
        self._table_abs  = None   # (x, y, w, h) absolute screen
        self._btn_abs    = None   # (cx, cy) absolute screen
        self._drag_start = None
        self._photo      = None   # keep PhotoImage reference alive

        self._build_ui()
        self.after(150, self._do_capture)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Instruction bar
        self._bar = ctk.CTkFrame(self, fg_color="#001f3f", corner_radius=0)
        self._bar.grid(row=0, column=0, sticky="ew")
        self._bar.grid_columnconfigure(0, weight=1)

        self._title_lbl = ctk.CTkLabel(
            self._bar, text="Aguardando captura...",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff",
        )
        self._title_lbl.grid(row=0, column=0, padx=16, pady=(10, 2), sticky="w")

        self._hint_lbl = ctk.CTkLabel(
            self._bar, text="",
            font=ctk.CTkFont(size=12), text_color="#aaaacc",
        )
        self._hint_lbl.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="w")

        # Canvas container (dark background so screenshot is framed)
        cf = ctk.CTkFrame(self, fg_color="#0d0d0d", corner_radius=0)
        cf.grid(row=1, column=0, sticky="nsew")
        cf.grid_columnconfigure(0, weight=1)
        cf.grid_rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(cf, bg="#0d0d0d", cursor="crosshair",
                                  highlightthickness=0)
        self._canvas.grid(row=0, column=0)
        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Motion>",          self._on_motion)

        # Bottom bar
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.grid(row=2, column=0, sticky="ew", padx=12, pady=8)

        ctk.CTkButton(
            bot, text="↺ Recapturar", width=110, height=32,
            fg_color="#3a3a3a", hover_color="#4a4a4a",
            command=self._do_capture,
        ).pack(side="left", padx=(0, 6))

        self._redo_table_btn = ctk.CTkButton(
            bot, text="Refazer Tabela", width=120, height=32,
            fg_color="#3a3a3a", hover_color="#4a4a4a",
            state="disabled", command=self._redo_table,
        )
        self._redo_table_btn.pack(side="left", padx=(0, 6))

        self._redo_btn_btn = ctk.CTkButton(
            bot, text="Refazer Botão", width=120, height=32,
            fg_color="#3a3a3a", hover_color="#4a4a4a",
            state="disabled", command=self._redo_btn_point,
        )
        self._redo_btn_btn.pack(side="left", padx=(0, 12))

        self._table_status = ctk.CTkLabel(
            bot, text="Tabela: —", font=ctk.CTkFont(size=11), text_color="#888888",
        )
        self._table_status.pack(side="left", padx=(0, 8))

        self._btn_status = ctk.CTkLabel(
            bot, text="Botão: —", font=ctk.CTkFont(size=11), text_color="#888888",
        )
        self._btn_status.pack(side="left")

        self._save_btn = ctk.CTkButton(
            bot, text="Salvar e Fechar", width=140, height=32,
            fg_color=_PURPLE, hover_color=_PURPLE_DARK,
            state="disabled", command=self._save,
        )
        self._save_btn.pack(side="right")

    # ── Capture ───────────────────────────────────────────────────────────────

    def _do_capture(self):
        """Hide all GUI windows, wait 700 ms, then screenshot the game."""
        self._title_lbl.configure(text="Capturando screenshot...", text_color="#aaaacc")
        self._hint_lbl.configure(text="Aguarde...")
        self.withdraw()
        self._parent.withdraw()
        self.update()
        self.after(700, self._take_screenshot)

    def _take_screenshot(self):
        error = None
        try:
            from rescue_tracker import config as cfg
            wins = gw.getWindowsWithTitle(cfg.WINDOW_TITLE)
            if not wins:
                raise RuntimeError(
                    f"Janela '{cfg.WINDOW_TITLE}' não encontrada. "
                    "Abra o jogo em Rescue Records e clique em '↺ Recapturar'."
                )
            win = wins[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.35)

            self._win_x, self._win_y = win.left, win.top
            img = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
            img_w, img_h = img.size

            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            max_w = min(sw - 60, 1400)
            max_h = min(sh - 280, 820)
            self._scale = min(max_w / img_w, max_h / img_h, 1.0)

            dw = int(img_w * self._scale)
            dh = int(img_h * self._scale)

            self._photo = ImageTk.PhotoImage(img.resize((dw, dh), Image.LANCZOS))
            self._canvas.configure(width=dw, height=dh)

            tw = dw + 24
            th = dh + 168
            self.geometry(f"{tw}x{th}+{(sw-tw)//2}+{(sh-th)//2}")

            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor="nw", image=self._photo, tags="bg")
            self._redraw_overlays()

        except Exception as exc:
            error = str(exc)

        finally:
            self._parent.deiconify()
            self.deiconify()
            self.lift()
            self.focus_force()

        if error:
            self._bar.configure(fg_color="#3d0000")
            self._title_lbl.configure(text="Erro ao capturar", text_color="#E74C3C")
            self._hint_lbl.configure(text=error, text_color="#ff8888")
        else:
            self._refresh_step_ui()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def _on_press(self, event):
        if self._step == "table":
            self._drag_start = (event.x, event.y)
        elif self._step == "button":
            s = self._scale
            self._btn_abs = (int(self._win_x + event.x / s),
                              int(self._win_y + event.y / s))
            self._canvas.delete("cursor_hint")
            self._draw_btn_overlay(event.x, event.y)
            self._step = "done"
            self._refresh_step_ui()

    def _on_drag(self, event):
        if self._step != "table" or not self._drag_start:
            return
        x0, y0 = self._drag_start
        self._canvas.delete("drag_rect")
        self._canvas.create_rectangle(
            x0, y0, event.x, event.y,
            outline="#00FF88", width=2, dash=(6, 4), tags="drag_rect",
        )

    def _on_release(self, event):
        if self._step != "table" or not self._drag_start:
            return
        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y
        self._drag_start = None
        self._canvas.delete("drag_rect")

        lx, rx = sorted([x0, x1])
        ty, by = sorted([y0, y1])
        if rx - lx < 10 or by - ty < 10:
            return

        s = self._scale
        self._table_abs = (
            int(self._win_x + lx / s),
            int(self._win_y + ty / s),
            int((rx - lx) / s),
            int((by - ty) / s),
        )
        self._draw_table_overlay(lx, ty, rx, by)
        self._step = "button"
        self._refresh_step_ui()

    def _on_motion(self, event):
        if self._step != "button":
            return
        self._canvas.delete("cursor_hint")
        r, x, y = 14, event.x, event.y
        kw = dict(fill="#FF6666", width=1, tags="cursor_hint")
        self._canvas.create_line(x - r, y, x + r, y, **kw)
        self._canvas.create_line(x, y - r, x, y + r, **kw)

    # ── Overlays ──────────────────────────────────────────────────────────────

    def _draw_table_overlay(self, x0, y0, x1, y1):
        self._canvas.delete("table_ov")
        self._canvas.create_rectangle(
            x0, y0, x1, y1, outline="#00FF88", width=3, tags="table_ov",
        )
        for px, py in [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]:
            self._canvas.create_oval(px-4, py-4, px+4, py+4,
                                      fill="#00FF88", outline="", tags="table_ov")
        self._canvas.create_text(
            x0+6, y0-6, anchor="sw", text="Tabela ✓", fill="#00FF88",
            font=("Consolas", 11, "bold"), tags="table_ov",
        )

    def _draw_btn_overlay(self, cx, cy):
        self._canvas.delete("btn_ov")
        r = 16
        self._canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                   outline="#FF4444", width=2, tags="btn_ov")
        kw = dict(fill="#FF4444", width=2, tags="btn_ov")
        self._canvas.create_line(cx-r, cy, cx+r, cy, **kw)
        self._canvas.create_line(cx, cy-r, cx, cy+r, **kw)
        self._canvas.create_text(
            cx+r+6, cy-6, anchor="sw", text="Botão ✓", fill="#FF4444",
            font=("Consolas", 11, "bold"), tags="btn_ov",
        )

    def _redraw_overlays(self):
        if self._table_abs:
            x, y, w, h = self._table_abs
            s = self._scale
            x0, y0 = (x - self._win_x) * s, (y - self._win_y) * s
            self._draw_table_overlay(x0, y0, x0 + w*s, y0 + h*s)
        if self._btn_abs:
            bx, by = self._btn_abs
            s = self._scale
            self._draw_btn_overlay((bx - self._win_x)*s, (by - self._win_y)*s)

    # ── Step UI ───────────────────────────────────────────────────────────────

    def _refresh_step_ui(self):
        title, hint, color, bg = self._STEPS.get(self._step, ("", "", "#fff", "#111"))
        self._title_lbl.configure(text=title, text_color=color)
        self._hint_lbl.configure(text=hint, text_color="#aaaacc")
        self._bar.configure(fg_color=bg)

        if self._table_abs:
            x, y, w, h = self._table_abs
            self._table_status.configure(
                text=f"Tabela: ({x}, {y}, {w}, {h})", text_color="#00FF88",
            )
            self._redo_table_btn.configure(state="normal")

        if self._btn_abs:
            bx, by = self._btn_abs
            self._btn_status.configure(
                text=f"Botão: ({bx}, {by})", text_color="#FF8888",
            )
            self._redo_btn_btn.configure(state="normal")

        self._save_btn.configure(
            state="normal" if (self._table_abs and self._btn_abs) else "disabled",
        )

    # ── Redo ──────────────────────────────────────────────────────────────────

    def _redo_table(self):
        self._table_abs = None
        self._canvas.delete("table_ov")
        self._table_status.configure(text="Tabela: —", text_color="#888888")
        self._redo_table_btn.configure(state="disabled")
        self._step = "table"
        self._refresh_step_ui()

    def _redo_btn_point(self):
        self._btn_abs = None
        self._canvas.delete("btn_ov")
        self._btn_status.configure(text="Botão: —", text_color="#888888")
        self._redo_btn_btn.configure(state="disabled")
        if self._step == "done":
            self._step = "button"
        self._refresh_step_ui()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not (self._table_abs and self._btn_abs):
            return

        try:
            # Salva em calibration.json próximo ao .exe (frozen) ou a gui.py (source)
            import json
            calib_path = _calib_json_path()
            os.makedirs(os.path.dirname(calib_path), exist_ok=True)
            with open(calib_path, "w", encoding="utf-8") as f:
                json.dump({
                    "TABLE_SCREEN_REGION": list(self._table_abs),
                    "NEXT_BUTTON_SCREEN_COORDS": list(self._btn_abs),
                }, f)

            # Quando rodando do código-fonte, também atualiza config.py no disco
            if not getattr(sys, "frozen", False):
                config_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "rescue_tracker", "config.py",
                )
                with open(config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                content = re.sub(
                    r"NEXT_BUTTON_SCREEN_COORDS\s*=\s*[^\n]*",
                    f"NEXT_BUTTON_SCREEN_COORDS = {self._btn_abs}",
                    content,
                )
                content = re.sub(
                    r"TABLE_SCREEN_REGION\s*=\s*[^\n]*",
                    f"TABLE_SCREEN_REGION = {self._table_abs}",
                    content,
                )
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # Aplica na memória em ambos os casos
            from rescue_tracker import config as cfg
            cfg.NEXT_BUTTON_SCREEN_COORDS = self._btn_abs
            cfg.TABLE_SCREEN_REGION = self._table_abs

        except Exception as exc:
            self._bar.configure(fg_color="#3d0000")
            self._title_lbl.configure(
                text=f"Erro ao salvar: {exc}", text_color="#E74C3C",
            )
            return

        if self._on_saved:
            self._on_saved(self._table_abs, self._btn_abs)
        self.destroy()


# ── Main application ───────────────────────────────────────────────────────────

class PullTrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Pull Tracker — Chaos Zero Nightmare")
        self.geometry("800x900")
        self.minsize(680, 640)

        _icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(_icon):
            self.iconbitmap(_icon)

        self._log_q: "queue.Queue[str]" = queue.Queue()
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

        _load_calibration()
        self._build_ui()
        self._poll_logs()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_settings()
        self._build_log_panel()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=_BG_HEADER, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hdr, text="Pull Tracker",
            font=ctk.CTkFont(size=28, weight="bold"), text_color=_PURPLE,
        ).grid(row=0, column=0, padx=20, pady=(16, 2), sticky="w")
        ctk.CTkLabel(
            hdr, text="Chaos Zero Nightmare — Rescue Records",
            font=ctk.CTkFont(size=13), text_color="#8888aa",
        ).grid(row=1, column=0, padx=20, pady=(0, 14), sticky="w")

    def _build_settings(self):
        s = ctk.CTkFrame(self)
        s.grid(row=1, column=0, sticky="ew", padx=16, pady=(12, 0))
        s.grid_columnconfigure(1, weight=1)
        r = 0

        # ── Section: capture settings ──────────────────────────────────────────
        ctk.CTkLabel(s, text="CONFIGURAÇÕES DE CAPTURA",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#666666").grid(
            row=r, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 6))
        r += 1

        # Page limit
        self._use_limit = ctk.BooleanVar(value=False)
        self._limit_val = ctk.StringVar(value="50")
        ctk.CTkCheckBox(s, text="Limite de páginas", variable=self._use_limit,
                         command=self._toggle_limit).grid(
            row=r, column=0, padx=12, pady=5, sticky="w")
        self._limit_entry = ctk.CTkEntry(s, textvariable=self._limit_val,
                                          width=75, state="disabled")
        self._limit_entry.grid(row=r, column=1, padx=0, pady=5, sticky="w")
        ctk.CTkLabel(s, text="páginas", text_color="#888888").grid(
            row=r, column=2, padx=(6, 12), sticky="w")
        r += 1

        # Output filename
        ctk.CTkLabel(s, text="Nome do arquivo").grid(
            row=r, column=0, padx=12, pady=5, sticky="w")
        self._fname = ctk.StringVar(value="rescue_data.json")
        ctk.CTkEntry(s, textvariable=self._fname).grid(
            row=r, column=1, columnspan=2, padx=(0, 12), pady=5, sticky="ew")
        r += 1

        # Output folder
        ctk.CTkLabel(s, text="Pasta de saída").grid(
            row=r, column=0, padx=12, pady=5, sticky="w")
        self._folder = ctk.StringVar(value="output")
        ctk.CTkEntry(s, textvariable=self._folder).grid(
            row=r, column=1, padx=0, pady=5, sticky="ew")
        ctk.CTkButton(s, text="📂", width=36, command=self._browse_folder).grid(
            row=r, column=2, padx=(4, 12), pady=5)
        r += 1

        # Speed slider
        ctk.CTkLabel(s, text="Velocidade de captura").grid(
            row=r, column=0, padx=12, pady=(10, 2), sticky="w")
        r += 1
        spd = ctk.CTkFrame(s, fg_color="transparent")
        spd.grid(row=r, column=0, columnspan=3, padx=12, pady=(0, 6), sticky="ew")
        spd.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(spd, text="Rápido", font=ctk.CTkFont(size=11),
                     text_color="#888888").grid(row=0, column=0, padx=(0, 8))
        self._speed = ctk.DoubleVar(value=1.5)
        ctk.CTkSlider(spd, from_=0.3, to=5.0, number_of_steps=47,
                      variable=self._speed,
                      command=lambda v: self._speed_lbl.configure(
                          text=f"{v:.1f}s entre páginas")).grid(
            row=0, column=1, sticky="ew")
        ctk.CTkLabel(spd, text="Lento", font=ctk.CTkFont(size=11),
                     text_color="#888888").grid(row=0, column=2, padx=(8, 0))
        self._speed_lbl = ctk.CTkLabel(spd, text="1.5s entre páginas",
                                        font=ctk.CTkFont(size=11), text_color=_PURPLE)
        self._speed_lbl.grid(row=1, column=0, columnspan=3, pady=(2, 0))
        r += 1

        # Debug toggle
        self._debug = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(s, text="Salvar screenshots de debug (output/debug/)",
                         variable=self._debug).grid(
            row=r, column=0, columnspan=3, padx=12, pady=(4, 8), sticky="w")
        r += 1

        # ── Section: calibration ───────────────────────────────────────────────
        ctk.CTkFrame(s, height=1, fg_color="#333333").grid(
            row=r, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 8))
        r += 1

        ctk.CTkLabel(s, text="CALIBRAÇÃO DE REGIÕES",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#666666").grid(
            row=r, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))
        r += 1

        # Current calibration values
        calib_row = ctk.CTkFrame(s, fg_color="transparent")
        calib_row.grid(row=r, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 4))
        calib_row.grid_columnconfigure(0, weight=1)
        calib_row.grid_columnconfigure(1, weight=1)

        self._calib_table_lbl = ctk.CTkLabel(
            calib_row, text="", font=ctk.CTkFont(family="Consolas", size=10),
            anchor="w",
        )
        self._calib_table_lbl.grid(row=0, column=0, sticky="w")

        self._calib_btn_lbl = ctk.CTkLabel(
            calib_row, text="", font=ctk.CTkFont(family="Consolas", size=10),
            anchor="w",
        )
        self._calib_btn_lbl.grid(row=0, column=1, sticky="w", padx=(8, 0))
        r += 1

        ctk.CTkButton(
            s, text="Calibrar Regiões  ▶",
            font=ctk.CTkFont(size=13),
            height=36, fg_color="#1a4a6e", hover_color="#1f5c8a",
            command=self._open_calibrate,
        ).grid(row=r, column=0, columnspan=3, padx=12, pady=(0, 8), sticky="ew")
        r += 1

        # ── Section: run ───────────────────────────────────────────────────────
        ctk.CTkFrame(s, height=1, fg_color="#333333").grid(
            row=r, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 8))
        r += 1

        self._start_btn = ctk.CTkButton(
            s, text="INICIAR CAPTURA",
            font=ctk.CTkFont(size=15, weight="bold"), height=44,
            fg_color=_PURPLE, hover_color=_PURPLE_DARK,
            command=self._toggle_capture,
        )
        self._start_btn.grid(row=r, column=0, columnspan=3, padx=12, pady=(0, 6), sticky="ew")
        r += 1

        self._progress = ctk.CTkProgressBar(s)
        self._progress.set(0)
        self._progress.grid(row=r, column=0, columnspan=3, padx=12, pady=(0, 4), sticky="ew")
        r += 1

        self._status_lbl = ctk.CTkLabel(s, text="Pronto.",
                                         font=ctk.CTkFont(size=12), text_color="#888888")
        self._status_lbl.grid(row=r, column=0, columnspan=3, pady=(0, 12))

        # Populate current calibration status from config
        self._refresh_calib_labels()

    def _build_log_panel(self):
        f = ctk.CTkFrame(self)
        f.grid(row=2, column=0, sticky="nsew", padx=16, pady=(12, 16))
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(f, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="LOG", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#666666").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="Limpar", width=60, height=24,
                      font=ctk.CTkFont(size=11), command=self._clear_log).grid(row=0, column=1)

        self._log_box = ctk.CTkTextbox(f, state="disabled",
                                        font=ctk.CTkFont(family="Consolas", size=11),
                                        wrap="word")
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

    # ── Calibration ───────────────────────────────────────────────────────────

    def _refresh_calib_labels(self):
        try:
            from rescue_tracker import config as cfg
            tbl = cfg.TABLE_SCREEN_REGION
            btn = cfg.NEXT_BUTTON_SCREEN_COORDS
            if tbl:
                self._calib_table_lbl.configure(
                    text=f"Tabela: {tbl}", text_color="#00FF88",
                )
            else:
                self._calib_table_lbl.configure(
                    text="Tabela: não calibrada", text_color="#888888",
                )
            if btn:
                self._calib_btn_lbl.configure(
                    text=f"Botão: {btn}", text_color="#FF8888",
                )
            else:
                self._calib_btn_lbl.configure(
                    text="Botão: não calibrado", text_color="#888888",
                )
        except Exception:
            pass

    def _open_calibrate(self):
        CalibrateWindow(self, on_saved=self._on_calibration_saved)

    def _on_calibration_saved(self, table_region, btn_coords):
        self._refresh_calib_labels()
        self._status_lbl.configure(
            text="Calibração salva com sucesso!", text_color=_GREEN,
        )

    # ── Capture controls ──────────────────────────────────────────────────────

    def _toggle_limit(self):
        self._limit_entry.configure(state="normal" if self._use_limit.get() else "disabled")

    def _browse_folder(self):
        d = filedialog.askdirectory(title="Selecionar pasta de saída")
        if d:
            self._folder.set(d)

    def _toggle_capture(self):
        if self._thread and self._thread.is_alive():
            self._stop_evt.set()
            self._status_lbl.configure(text="Parando...", text_color=_ORANGE)
        else:
            self._begin_capture()

    def _begin_capture(self):
        import ctypes as _ct
        if not _ct.windll.shell32.IsUserAnAdmin():
            self._status_lbl.configure(
                text="⚠ Execute como Administrador! (o jogo roda elevado)",
                text_color="#E74C3C",
            )
            return

        self._stop_evt.clear()
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        self._start_btn.configure(text="PARAR CAPTURA",
                                   fg_color=_RED, hover_color=_RED_DARK)
        self._status_lbl.configure(text="Iniciando...", text_color=_ORANGE)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self.iconify()   # minimiza para liberar foco ao jogo
        self._thread.start()

    def _finish(self, ok: bool, msg: str):
        self.deiconify()  # restaura janela ao finalizar captura
        self.lift()
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(1.0 if ok else 0.0)
        self._start_btn.configure(text="INICIAR CAPTURA",
                                   fg_color=_PURPLE, hover_color=_PURPLE_DARK)
        self._status_lbl.configure(text=msg, text_color=_GREEN if ok else "#E74C3C")

    # ── Worker thread ─────────────────────────────────────────────────────────

    def _worker(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from rescue_tracker import config as cfg
        from rescue_tracker.main import run

        cfg.DELAY_BETWEEN_PAGES = round(self._speed.get(), 1)
        cfg.DEBUG_SAVE_SCREENSHOTS = self._debug.get()

        folder = self._folder.get().strip() or "output"
        fname  = self._fname.get().strip()  or "rescue_data.json"
        if not fname.endswith(".json"):
            fname += ".json"
        output = os.path.join(folder, fname)

        limit = None
        if self._use_limit.get():
            try:
                v = int(self._limit_val.get())
                if v > 0:
                    limit = v
            except ValueError:
                pass

        def on_progress(page: int, total):
            text = f"Página {page}/{total}" if total else f"Capturando página {page}..."
            self.after(0, lambda: self._status_lbl.configure(text=text))

        try:
            run(max_pages=limit, output_path=output,
                stop_event=self._stop_evt, on_progress=on_progress,
                log_handler=_QueueHandler(self._log_q))
            if self._stop_evt.is_set():
                self.after(0, self._finish, True, "Captura interrompida pelo usuário.")
            else:
                self.after(0, self._finish, True, "Concluído com sucesso!")
        except RuntimeError as exc:
            self.after(0, self._finish, False, f"Erro: {exc}")
        except Exception as exc:
            self.after(0, self._finish, False, f"Erro inesperado: {exc}")

    # ── Log ───────────────────────────────────────────────────────────────────

    def _poll_logs(self):
        while not self._log_q.empty():
            try:
                self._append_log(self._log_q.get_nowait())
            except queue.Empty:
                break
        self.after(100, self._poll_logs)

    def _append_log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")


def main():
    app = PullTrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
