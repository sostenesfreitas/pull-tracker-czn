#!/usr/bin/env python3
"""
Ponto de entrada principal do Pull Tracker.

Uso básico:
    python run.py

Limitar páginas (teste):
    python run.py --pages 15

Salvar em arquivo específico:
    python run.py --output output/teste.json

Combinar:
    python run.py --pages 15 --output output/teste.json

Desativar screenshots de debug:
    python run.py --no-debug

Ver ajuda completa:
    python run.py --help
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from rescue_tracker.main import main

if __name__ == "__main__":
    main()
