# main.py — Entry point do Pull Tracker

import argparse
import logging
import os
import sys
import threading
import time
from typing import Callable, Optional

from . import config
from . import capturer
from . import navigator
from . import parser
from . import analyzer


# ── Logging ────────────────────────────────────────────────────────────────────

def _setup_logging(extra_handler: Optional[logging.Handler] = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    fh = logging.FileHandler(
        os.path.join(config.OUTPUT_DIR, "rescue_tracker.log"), encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if extra_handler:
        root.addHandler(extra_handler)
    else:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pull-tracker",
        description="Captura o histórico de pulls (Rescue Records) de Chaos Zero Nightmare.",
    )
    p.add_argument("--pages", "-p", type=int, default=None, metavar="N",
                   help="Limita a captura às primeiras N páginas.")
    p.add_argument("--output", "-o", type=str, default=None, metavar="ARQUIVO",
                   help=f"Caminho do JSON de saída. Padrão: {config.OUTPUT_DIR}/{config.OUTPUT_FILE}")
    p.add_argument("--debug", action="store_true", default=config.DEBUG_SAVE_SCREENSHOTS,
                   help="Salva screenshots em output/debug/.")
    p.add_argument("--no-debug", action="store_true",
                   help="Desativa o salvamento de screenshots de debug.")
    return p.parse_args()


# ── Core run ───────────────────────────────────────────────────────────────────

def run(
    max_pages: Optional[int] = None,
    output_path: Optional[str] = None,
    stop_event: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
    log_handler: Optional[logging.Handler] = None,
) -> None:
    """
    Executa o ciclo completo: captura → parse → análise → exportação.

    Args:
        max_pages:    Número máximo de páginas (None = todas).
        output_path:  Caminho do JSON de saída (None = usa config.py).
        stop_event:   threading.Event — sinaliza parada antecipada.
        on_progress:  Callback (page_num, max_pages) chamado a cada página.
        log_handler:  Handler extra de logging (usado pela GUI).
    """
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    if config.DEBUG_SAVE_SCREENSHOTS:
        os.makedirs(config.DEBUG_DIR, exist_ok=True)

    _setup_logging(log_handler)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Pull Tracker — Chaos Zero Nightmare")
    if max_pages:
        logger.info("Modo de teste: capturando até %d página(s).", max_pages)
    logger.info("=" * 60)

    # ── 1. Localizar e focar a janela ──────────────────────────────────────────
    window = capturer.find_game_window()
    if window is None:
        msg = f"Janela '{config.WINDOW_TITLE}' não encontrada. Abra o jogo e tente novamente."
        logger.error(msg)
        raise RuntimeError(msg)

    if not capturer.focus_game_window(window):
        logger.warning("Não foi possível focar a janela automaticamente. Continuando...")

    logger.info("Aguardando 2 segundos antes de iniciar a captura...")
    time.sleep(2)

    # ── 2. Iterar páginas ──────────────────────────────────────────────────────
    all_entries: list = []
    total_pages = 0

    for page_num in navigator.iter_pages(window, max_pages=max_pages):
        if stop_event and stop_event.is_set():
            logger.info("Captura interrompida pelo usuário na página %d.", page_num)
            break

        total_pages = page_num

        if on_progress:
            on_progress(page_num, max_pages)

        logger.info("── Capturando página %d%s ──",
                    page_num, f"/{max_pages}" if max_pages else "")

        try:
            table_img = capturer.screenshot_table(window)
            capturer.save_debug_screenshot(table_img, page_num)
            page_entries = parser.parse_page(table_img, page_number=page_num)
            all_entries.extend(page_entries)

            logger.info("Página %d: %d pull(s) | notáveis: %d",
                        page_num, len(page_entries),
                        sum(1 for e in page_entries if e.rarity >= 4))

        except Exception as exc:
            logger.error("Erro ao processar página %d: %s", page_num, exc)

    logger.info("Captura concluída: %d página(s), %d pull(s) total.", total_pages, len(all_entries))

    if not all_entries:
        logger.warning("Nenhum pull capturado. Verifique TABLE_SCREEN_REGION no config.py.")
        return

    # ── 3. Calcular pity ───────────────────────────────────────────────────────
    logger.info("Calculando pity...")
    notables, current_pity = analyzer.calculate_pity(all_entries)
    logger.info("Notáveis: 5★ × %d  |  4★ × %d",
                sum(1 for e in notables if e.rarity == 5),
                sum(1 for e in notables if e.rarity == 4))

    # ── 4. Gerar e salvar JSON ─────────────────────────────────────────────────
    output_data = analyzer.build_output(notables, all_entries, current_pity)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        import json
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        path = output_path
        logger.info("Resultado salvo em: %s", path)
    else:
        path = analyzer.save_output(output_data)

    logger.info("=" * 60)
    logger.info("Concluído! → %s", path)
    logger.info(
        "Total: %d pulls | 5★: %d (pity médio %.1f) | 4★: %d (pity médio %.1f)",
        output_data["total_pulls"],
        output_data["summary"]["five_star_count"],
        output_data["summary"]["average_pity_5star"],
        output_data["summary"]["four_star_count"],
        output_data["summary"]["average_pity_4star"],
    )
    logger.info("Pity atual por banner: %s", output_data["summary"]["current_pity_by_banner"])
    logger.info("=" * 60)


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    if args.no_debug:
        config.DEBUG_SAVE_SCREENSHOTS = False
    elif args.debug:
        config.DEBUG_SAVE_SCREENSHOTS = True

    try:
        run(max_pages=args.pages, output_path=args.output)
    except RuntimeError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
