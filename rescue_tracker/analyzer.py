# analyzer.py — Cálculo de pity e geração do JSON final

import json
import logging
import os
from collections import defaultdict
from typing import Dict, List, Any

from .parser import PullEntry
from . import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Cálculo de pity
# ──────────────────────────────────────────────────────────────

def calculate_pity(all_entries: List[PullEntry]) -> tuple:
    """
    Atribui `pity` e `pull_number` a cada entrada notável (4★/5★).

    Regras do jogo:
    ┌──────────────────────────────────────────────────────────────┐
    │  • A tela exibe pulls do MAIS RECENTE (topo) → MAIS ANTIGO   │
    │    Invertemos para calcular pity na ordem cronológica correta │
    │  • Pity é contado por banner (Rescue Type)                   │
    │  • Pull 5★ → registra pity = contador atual → RESET para 0   │
    │  • Pull 4★ → registra pity = contador atual → NÃO reseta     │
    │  • Pull 3★ → apenas incrementa o contador, não é registrado  │
    │  • Pity máximo: MAX_PITY_5STAR (padrão 70) — hard cap        │
    └──────────────────────────────────────────────────────────────┘

    Returns:
        (notables, current_pity_by_banner)
    """
    chronological = list(reversed(all_entries))
    counters: Dict[str, int] = defaultdict(int)
    notables: List[PullEntry] = []
    global_pull_number = 0

    for entry in chronological:
        banner = entry.rescue_type or "Unknown"
        counters[banner] += 1
        global_pull_number += 1
        entry.pull_number = global_pull_number

        if entry.rarity == 5:
            entry.pity = counters[banner]
            counters[banner] = 0
            notables.append(entry)
            logger.info(
                "5★ '%s' | banner='%s' | pity=%d | pull #%d",
                entry.name, banner, entry.pity, global_pull_number,
            )

        elif entry.rarity == 4:
            entry.pity = counters[banner]
            notables.append(entry)
            logger.info(
                "4★ '%s' | banner='%s' | pity=%d | pull #%d",
                entry.name, banner, entry.pity, global_pull_number,
            )

    current_pity = dict(counters)
    logger.info("Pity atual por banner: %s", current_pity)

    # ── Validação de pity ──────────────────────────────────────
    _validate_pity(notables)

    return notables, current_pity


def _validate_pity(notables: List[PullEntry]) -> None:
    """
    Verifica se algum pity ultrapassa o hard cap do jogo (MAX_PITY_5STAR = 70).

    Valores acima do cap indicam erro de captura (OCR pulou linhas, página
    repetida, etc.) e são marcados com  data_warning = "pity_exceeds_cap".
    O pity NÃO é alterado para preservar os dados brutos — o frontend
    pode usar o campo warning para exibir um indicador de dados suspeitos.
    """
    cap = config.MAX_PITY_5STAR
    warnings = 0

    for entry in notables:
        if entry.rarity == 5 and entry.pity > cap:
            entry.data_warning = "pity_exceeds_cap"
            logger.warning(
                "⚠ PITY INVÁLIDO: '%s' (5★) pity=%d > cap=%d | pull #%d | banner='%s'\n"
                "  Causa provável: OCR perdeu linhas ou página duplicada.\n"
                "  Verifique output/debug/ para inspecionar as páginas.",
                entry.name, entry.pity, cap, entry.pull_number, entry.rescue_type,
            )
            warnings += 1

    if warnings:
        logger.warning(
            "%d pull(s) com pity acima do cap (%d). "
            "Verifique os screenshots de debug em output/debug/.",
            warnings, cap,
        )


# ──────────────────────────────────────────────────────────────
# Geração do resumo
# ──────────────────────────────────────────────────────────────

def _build_summary(
    notables: List[PullEntry],
    total_pulls: int,
    current_pity: Dict[str, int],
) -> Dict[str, Any]:
    five_stars = [e for e in notables if e.rarity == 5]
    four_stars = [e for e in notables if e.rarity == 4]

    avg_pity_5 = (
        round(sum(e.pity for e in five_stars) / len(five_stars), 1)
        if five_stars else 0.0
    )
    avg_pity_4 = (
        round(sum(e.pity for e in four_stars) / len(four_stars), 1)
        if four_stars else 0.0
    )

    suspicious = [e for e in notables if e.data_warning]

    return {
        "five_star_count":        len(five_stars),
        "four_star_count":        len(four_stars),
        "average_pity_5star":     avg_pity_5,
        "average_pity_4star":     avg_pity_4,
        "current_pity_by_banner": current_pity,
        "pity_cap":               config.MAX_PITY_5STAR,
        # Pulls com dados suspeitos (pity > cap = OCR perdeu linhas)
        "suspicious_pulls":       len(suspicious),
    }


# ──────────────────────────────────────────────────────────────
# Serialização JSON
# ──────────────────────────────────────────────────────────────

def build_output(
    notables: List[PullEntry],
    all_entries: List[PullEntry],
    current_pity: Dict[str, int],
    banner_name: str = "Combatant Rescue Rate Up",
) -> Dict[str, Any]:
    """
    Monta o dicionário de saída no formato especificado.

    Args:
        notables:      Pulls 4★/5★ com pity calculado (mais antigo → mais recente).
        all_entries:   Todos os pulls (incluindo 3★), para contar total.
        current_pity:  Pity acumulado atual por banner (pulls desde o último 5★).
        banner_name:   Nome do banner principal (inferido dos dados).
    """
    from collections import Counter

    # Infere o banner mais frequente nos dados
    banner_counts = Counter(e.rescue_type for e in all_entries if e.rescue_type)
    if banner_counts:
        banner_name = banner_counts.most_common(1)[0][0]

    characters = [
        {
            "name":          entry.name,
            "rarity":        entry.rarity,
            "pity":          entry.pity,
            "rescue_type":   entry.rescue_type,
            "timestamp":     entry.timestamp,
            "pull_number":   entry.pull_number,
            "image":         entry.image,
            "class":         entry.char_class,
            "attribute":     entry.attribute,
            "rarity_source": entry.rarity_source,
            "data_warning":  entry.data_warning,  # "pity_exceeds_cap" = dado suspeito
        }
        for entry in notables
    ]

    return {
        "banner":      banner_name,
        "total_pulls": len(all_entries),
        "characters":  characters,
        "summary":     _build_summary(notables, len(all_entries), current_pity),
    }


def save_output(data: Dict[str, Any]) -> str:
    """Salva o JSON no disco e retorna o caminho do arquivo."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(config.OUTPUT_DIR, config.OUTPUT_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Resultado salvo em: %s", path)
    return path
