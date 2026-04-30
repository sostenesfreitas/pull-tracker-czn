# Pull Tracker — Chaos Zero Nightmare

Captura automaticamente todo o histórico de pulls (Rescue Records) do **Chaos Zero Nightmare**, calcula pity por banner e exporta para JSON.

---

## Visualizador Web

Depois de gerar o JSON, importe-o no site para visualizar seu histórico com gráficos e estatísticas:

**[🌐 pull-tracker-czn.lovable.app](https://pull-tracker-czn.lovable.app)**

---

## Download Rápido

Não quer instalar Python? Baixe o executável pronto:

**[⬇ Releases → PullTracker.exe](../../releases/latest)**

> **Importante:** o jogo roda como Administrador. Execute o `PullTracker.exe` também como Administrador (clique direito → "Executar como administrador").

---

## Interface Gráfica (GUI)

### Requisitos

| Requisito | Link |
|---|---|
| Python 3.10+ | https://www.python.org/downloads/ |
| Tesseract OCR | https://github.com/UB-Mannheim/tesseract/wiki |
| Dependências | `pip install -r requirements.txt` |

### Iniciando

```bash
# Execute como Administrador
python gui.py
```

> O jogo precisa estar aberto na tela de **Rescue Records** antes de iniciar.

---

## Configuração (primeiro uso)

### 1. Calibrar as regiões

Na GUI, clique em **"Calibrar Regiões ▶"**.

A janela de calibração vai:
1. Tirar um screenshot do jogo automaticamente
2. Exibir a imagem com cursor de mira

**Passo 1 — Área da tabela (barra laranja):**
Arraste um retângulo sobre as 5 linhas de dados (sem incluir o cabeçalho).

**Passo 2 — Botão ">" (barra azul):**
Clique no centro do botão de próxima página.

Clique em **"Salvar e Fechar"** — as coordenadas são salvas automaticamente em `config.py`.

### 2. Ajustar velocidade de captura

Use o slider **"Velocidade de captura"** (0.3s → 5.0s entre páginas).
Aumente se o jogo demorar para carregar cada página.

### 3. Definir arquivo de saída

| Campo | Descrição |
|---|---|
| Nome do arquivo | Nome do `.json` gerado (ex.: `meu_historico.json`) |
| Pasta de saída | Pasta onde o arquivo será salvo (botão 📂 para navegar) |

---

## Usando a GUI

1. Abra o jogo na tela de **Rescue Records** (primeira página)
2. Execute o Pull Tracker **como Administrador**
3. (Primeiro uso) Clique em **"Calibrar Regiões ▶"** e siga os passos
4. Configure limite de páginas se desejar (checkbox "Limite de páginas")
5. Clique em **"INICIAR CAPTURA"**

A janela será minimizada automaticamente para liberar o foco ao jogo. Ao concluir, a janela volta ao primeiro plano com o resultado no log.

---

## Linha de Comando (CLI)

```bash
# Captura todo o histórico
python run.py

# Limita a N páginas (útil para testes)
python run.py --pages 15

# Define arquivo de saída personalizado
python run.py --output meu_historico.json

# Desativa screenshots de debug
python run.py --no-debug
```

---

## Formato do JSON de saída

```json
{
  "total_pulls": 600,
  "summary": {
    "five_star_count": 3,
    "four_star_count": 45,
    "average_pity_5star": 65.3,
    "average_pity_4star": 8.1,
    "current_pity_by_banner": {
      "Seasonal Combatant Rescue Rate-Up": 27
    }
  },
  "characters": [
    {
      "name": "Yuri",
      "rarity": 5,
      "pity": 75,
      "rescue_type": "Seasonal Combatant Rescue Rate-Up",
      "timestamp": "2026-04-08 20:14:32",
      "pull_number": 1
    }
  ]
}
```

---

## Estrutura do projeto

```
pull-tracker-czn/
├── gui.py                  # Interface gráfica (recomendado)
├── run.py                  # CLI
├── build.bat               # Gera PullTracker.exe
├── icon.ico                # Ícone do executável
├── PullTracker.manifest    # Manifesto UAC (pede admin ao abrir .exe)
├── requirements.txt
└── rescue_tracker/
    ├── config.py           # Coordenadas e configurações
    ├── capturer.py         # Screenshots e controle de janela
    ├── navigator.py        # Navegação entre páginas
    ├── parser.py           # OCR e detecção de raridade
    ├── analyzer.py         # Cálculo de pity e JSON
    └── characters.json     # Banco de personagens
```

---

## Compilando o executável

```bat
build.bat
```

Gera `dist/PullTracker.exe` — arquivo único, sem necessidade de instalar Python. O manifesto UAC solicita elevação automaticamente ao abrir.

---

## Dicas

- **Screenshots de debug** ficam em `output/debug/` — útil para inspecionar o que o OCR leu em cada página.
- **Log completo** em `output/rescue_tracker.log`.
- Se o OCR perder linhas, verifique se a área da tabela está bem calibrada (recalibre com **"Calibrar Regiões ▶"**).
- `data_warning: "pity_exceeds_cap"` no JSON indica falha de OCR — o pity calculado passou de 70 (limite do jogo).
