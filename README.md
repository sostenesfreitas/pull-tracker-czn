# Pull Tracker — Chaos Zero Nightmare

Sistema automatizado para capturar e processar o histórico de pulls
(Rescue Records) do jogo **Chaos Zero Nightmare**.

---

## Estrutura do Projeto

```
pull-tracker/
├── run.py                      # Ponto de entrada principal
├── calibrate.py                # Ferramenta de calibração de regiões
├── requirements.txt
├── rescue_tracker/
│   ├── __init__.py
│   ├── config.py               # Configurações ajustáveis
│   ├── capturer.py             # Screenshot + controle de janela
│   ├── navigator.py            # Navegação entre páginas
│   ├── parser.py               # OCR + detecção de raridade por cor
│   ├── analyzer.py             # Cálculo de pity e geração do JSON
│   └── main.py                 # Orquestração do fluxo completo
└── output/
    ├── rescue_data.json        # Resultado final
    ├── rescue_tracker.log      # Log de execução
    └── debug/                  # Screenshots de debug (uma por página)
```

---

## Pré-requisitos

### 1. Python 3.10+

Verifique com:
```
python --version
```

### 2. Tesseract OCR

Baixe e instale: https://github.com/UB-Mannheim/tesseract/wiki

Após instalar, anote o caminho (ex.: `C:\Program Files\Tesseract-OCR\tesseract.exe`)
e configure em `rescue_tracker/config.py`:
```python
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

### 3. Dependências Python

```bash
pip install -r requirements.txt
```

---

## Configuração (obrigatório antes do primeiro uso)

### Passo 1 — Abra o jogo e navegue até Rescue Records

Deixe a primeira página do histórico de pulls visível na tela.

### Passo 2 — Execute a calibração

```bash
python calibrate.py
```

O script abrirá uma janela interativa onde você:
1. Arrasta para selecionar a **região da tabela** (as 5 linhas de pulls)
2. Arrasta para selecionar a **região do botão ">"** (próxima página)

As coordenadas serão impressas no terminal. Copie-as para `rescue_tracker/config.py`:

```python
TABLE_REGION       = (x, y, largura, altura)
NEXT_BUTTON_REGION = (x, y, largura, altura)
```

### Passo 3 (opcional) — Ajuste as cores

Se a detecção de raridade não funcionar bem, ajuste em `config.py`:

```python
COLOR_5STAR      = (176, 127, 204)   # RGB do lilás/roxo
COLOR_4STAR      = (200, 168, 75)    # RGB do dourado
COLOR_TOLERANCE  = 35                # margem de tolerância
```

---

## Uso

```bash
# Captura todo o histórico
python run.py

# Limita a N páginas (útil para testes)
python run.py --pages 15

# Define um arquivo de saída personalizado
python run.py --output meu_historico.json

# Desativa salvamento de screenshots de debug
python run.py --no-debug
```

O programa irá:
1. Localizar e focar a janela do jogo
2. Capturar todas as páginas do Rescue Records automaticamente
3. Identificar personagens 4★ e 5★ pela cor do nome ou pelo banco de dados de personagens
4. Calcular o pity de cada pull por banner
5. Salvar o resultado em `output/rescue_data.json`

---

## Formato do JSON de saída

```json
{
  "banner": "Combatant Rescue Rate Up",
  "total_pulls": 600,
  "characters": [
    {
      "name": "Yuri",
      "rarity": 5,
      "pity": 75,
      "rescue_type": "Combatant Rescue Rate Up",
      "timestamp": "2026-04-08 20:14:32",
      "pull_number": 1,
      "image": "url_da_imagem",
      "class": "Warrior",
      "attribute": "Fire",
      "rarity_source": "exact",
      "data_warning": null
    }
  ],
  "summary": {
    "five_star_count": 3,
    "four_star_count": 45,
    "average_pity_5star": 65.3,
    "average_pity_4star": 8.1,
    "current_pity_by_banner": {
      "Combatant Rescue Rate Up": 27
    },
    "suspicious_pulls": 0
  }
}
```

---

## Dicas de uso

- **Screenshots de debug**: habilitados por padrão em `config.py` (`DEBUG_SAVE_SCREENSHOTS = True`).
  Cada página capturada é salva em `output/debug/` para inspecionar o que o OCR está lendo.

- **Log completo**: disponível em `output/rescue_tracker.log`.

- **Velocidade**: ajuste `DELAY_BETWEEN_PAGES` em `config.py` se o jogo demorar mais para carregar as páginas.

- **Múltiplos banners**: o sistema separa automaticamente por `rescue_type` e calcula pity independente para cada banner.

- **`data_warning: "pity_exceeds_cap"`**: indica possível falha de OCR — o pity calculado ultrapassou 70 (limite máximo do jogo). Verifique o screenshot de debug da página correspondente.

- **Banco de personagens**: o arquivo `characters (1).json` contém o cadastro de todos os personagens com raridade, classe, atributo e URL de imagem. Personagens não encontrados usam detecção por cor como fallback.
