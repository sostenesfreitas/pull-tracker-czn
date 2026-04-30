# config.py — Configurações ajustáveis do Pull Tracker
# ─────────────────────────────────────────────────────────────────
# COMO ENCONTRAR AS COORDENADAS:
#   1. Abra o jogo na tela de Rescue Records
#   2. Abra o Paint e tire um print (Win+PrintScreen)
#   3. Abra o print no Paint e passe o mouse em cima de cada região
#   4. O canto inferior esquerdo do Paint mostra os pixels exatos
#   5. Cole os valores aqui em NEXT_BUTTON_SCREEN_COORDS e TABLE_SCREEN_REGION
# ─────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────
# JANELA DO JOGO
# ──────────────────────────────────────────────
WINDOW_TITLE = "Chaos Zero Nightmare"

# ──────────────────────────────────────────────
# DELAYS
# ──────────────────────────────────────────────
DELAY_BETWEEN_PAGES = 1.5   # segundos após clicar em "próxima página"
DELAY_AFTER_FOCUS   = 0.5   # segundos após focar a janela

# ══════════════════════════════════════════════════════════════════
# COORDENADAS ABSOLUTAS DE TELA  ← PREENCHA AQUI
# (mais fácil: passe o mouse no Paint e leia os pixels no canto inf.)
# ══════════════════════════════════════════════════════════════════

# Centro do botão ">" de próxima página
# Confirmado pelo Print no Paint: cursor em (1079, 914)
NEXT_BUTTON_SCREEN_COORDS = (1088, 917)

# Região da tabela de pulls em coords absolutas de tela: (x, y, largura, altura)
# x,y = canto superior esquerdo da PRIMEIRA linha de dados (abaixo do header)
# Para encontrar: passe o mouse no Paint no início e fim da tabela
TABLE_SCREEN_REGION = (256, 460, 1401, 272)

# ──────────────────────────────────────────────
# REGIÕES RELATIVAS À JANELA (alternativa)
# Usadas SOMENTE se as coords absolutas acima forem None.
# Execute  python calibrate.py  para calibrar visualmente.
# ──────────────────────────────────────────────

# Região das 5 linhas de dados (relativa à janela)
TABLE_REGION = (186, 347, 1069, 215)

# Região do botão ">" (relativa à janela)
NEXT_BUTTON_REGION = (796, 673, 48, 48)

# Altura aproximada de cada linha da tabela (pixels)
ROW_HEIGHT = 43

# Número de pulls por página
PULLS_PER_PAGE = 5

# ──────────────────────────────────────────────
# REGRAS DE PITY DO JOGO
# ──────────────────────────────────────────────

# Pull garantido de 5★ (pity hard cap)
MAX_PITY_5STAR = 70

# Pull garantido de 4★ (se houver — deixe None se não tiver cap definido)
MAX_PITY_4STAR = None

# ──────────────────────────────────────────────
# PROPORÇÕES DAS COLUNAS DA TABELA
# Medidas no screenshot: Type | Rescue List | Rescue Type | Rescue Time
# Larguras aproximadas:   217  |     321     |     219     |     312
# ──────────────────────────────────────────────
# (usado em parser.py → _split_row_into_columns)
COL_RATIOS = (0.20, 0.30, 0.21, 0.29)

# ──────────────────────────────────────────────
# LOOKUP DE PERSONAGENS
# ──────────────────────────────────────────────

# Arquivo JSON com nome → raridade (fonte principal de detecção)
import os as _os
CHARACTERS_FILE = _os.path.join(_os.path.dirname(__file__), "characters.json")

# Similaridade mínima para o fuzzy match (0.0 a 1.0)
# 0.75 = aceita até ~2 caracteres errados em nomes curtos
FUZZY_MATCH_CUTOFF = 0.75

# ──────────────────────────────────────────────
# DETECÇÃO DE CORES (fallback quando nome não está no lookup)
# Calibradas com screenshot real (página 19):
#   Diana (5★) → roxo/lilás  #9664C8 ≈ RGB(150, 100, 200)
#   Mika  (4★) → laranja     #E08020 ≈ RGB(224, 128, 32)
#   Raidel/Zatera/Nakia (3★) → cinza claro (sem saturação)
# ──────────────────────────────────────────────

# Cor do nome 5★ — roxo/lilás (ex.: "Diana" aparece em #9664C8)
COLOR_5STAR = (150, 100, 200)

# Cor do nome 4★ — laranja/âmbar (ex.: "Mika" aparece em #E08020)
# ATENÇÃO: NÃO é dourado — é laranja saturado.
COLOR_4STAR = (224, 128, 32)

# Margem de tolerância (distância euclidiana no espaço RGB)
# 40 é seguro para absorver variação de compressão/antialiasing
COLOR_TOLERANCE = 40

# Cor do botão ATIVO (fundo cinza claro, visível no screenshot como botão ">")
# O botão ">" ativo tem fundo ~RGB(210,210,210) no screenshot
BUTTON_ACTIVE_COLOR  = (210, 210, 210)
BUTTON_ACTIVE_TOL    = 55

# Cor do botão INATIVO (fundo cinza médio, visível no screenshot como botão "<")
# O botão "<" inativo tem fundo ~RGB(155,155,155) no screenshot
BUTTON_INACTIVE_COLOR = (155, 155, 155)
BUTTON_INACTIVE_TOL   = 45

# ──────────────────────────────────────────────
# OCR (Tesseract)
# ──────────────────────────────────────────────
# Caminho para o executável do Tesseract (Windows)
# Deixe None para usar o PATH do sistema.
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Idioma OCR
OCR_LANG = "eng"

# Config extra para pytesseract (PSM 6 = bloco de texto uniforme)
OCR_CONFIG = "--psm 6"

# ──────────────────────────────────────────────
# SAÍDA
# ──────────────────────────────────────────────
OUTPUT_DIR  = "output"
OUTPUT_FILE = "rescue_data.json"

# ──────────────────────────────────────────────
# DEBUG / LOG
# ──────────────────────────────────────────────
DEBUG_SAVE_SCREENSHOTS = True   # salva cada página capturada em output/debug/
DEBUG_DIR = "output/debug"
