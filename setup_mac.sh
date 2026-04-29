#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Pull Tracker — Chaos Zero Nightmare
#  Script de instalação para macOS
# ═══════════════════════════════════════════════════════════════

set -e
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Pull Tracker — Instalação (macOS)"
echo "════════════════════════════════════════════════════════"
echo ""

# ── 1. Verifica Homebrew ──────────────────────────────────────
if ! command -v brew &>/dev/null; then
  echo "[!] Homebrew não encontrado. Instalando..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Adiciona brew ao PATH (Apple Silicon)
  if [[ -f /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
else
  echo "[OK] Homebrew encontrado: $(brew --version | head -1)"
fi

# ── 2. Verifica Python ───────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo ""
  echo "[!] Python 3 não encontrado. Instalando via Homebrew..."
  brew install python
else
  PY_VER=$(python3 --version 2>&1)
  echo "[OK] $PY_VER"
fi

# ── 3. Instala Tesseract OCR ─────────────────────────────────
echo ""
if command -v tesseract &>/dev/null; then
  echo "[OK] Tesseract já instalado: $(tesseract --version 2>&1 | head -1)"
else
  echo "Instalando Tesseract OCR..."
  brew install tesseract
  echo "[OK] Tesseract instalado."
fi

# ── 4. Dependências Python ───────────────────────────────────
echo ""
echo "Instalando dependências Python..."
pip3 install --upgrade pip --quiet

# pygetwindow no macOS precisa de pyobjc
pip3 install pyobjc-core pyobjc-framework-Cocoa --quiet 2>/dev/null || true
pip3 install -r requirements.txt

echo ""
echo "[OK] Dependências instaladas."

# ── 5. Permissão de acessibilidade (macOS) ───────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  PERMISSÃO NECESSÁRIA — Acessibilidade"
echo "════════════════════════════════════════════════════════"
echo ""
echo "  Para capturar a tela e controlar o mouse automaticamente,"
echo "  o Terminal precisa de permissão de Acessibilidade."
echo ""
echo "  Vá em:"
echo "    Preferências do Sistema → Privacidade e Segurança"
echo "    → Acessibilidade → marque 'Terminal' (ou seu app de terminal)"
echo ""
echo "  E também em:"
echo "    → Gravação de Tela → marque 'Terminal'"
echo ""
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true

# ── 6. Pronto ────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Instalação concluída!"
echo ""
echo "  PRÓXIMOS PASSOS:"
echo ""
echo "  1. Tente primeiro o método mais confiável (sem OCR):"
echo "       python3 leitor_cache.py"
echo "     Abra o Rescue Records no jogo antes de rodar."
echo ""
echo "  2. Se o jogo não tiver API via cache, calibre as regiões:"
echo "       python3 calibrar.py"
echo ""
echo "  3. Depois rode o tracker:"
echo "       python3 run.py"
echo "════════════════════════════════════════════════════════"
echo ""
