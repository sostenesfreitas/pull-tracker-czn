#!/usr/bin/env python3
"""
leitor_cache.py — Extração de dados via arquivos de cache do jogo
═══════════════════════════════════════════════════════════════════

Como funciona:
  Muitos jogos usam um WebView embutido (Chromium) para exibir o
  histórico de pulls. O WebView cacheia as requisições HTTP — incluindo
  a URL com o token de autenticação. Este script:

    1. Localiza a pasta de instalação do jogo
    2. Varre os arquivos de cache em busca de URLs de API
    3. Testa se a URL retorna dados de pull
    4. Se sim: baixa TODO o histórico via API, sem OCR

Como usar:
    python leitor_cache.py

  Abra o Rescue Records no jogo ANTES de rodar este script
  (para garantir que o cache foi gerado).
"""

import os
import re
import sys
import json
import time
import platform
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

_OS = platform.system()

# ──────────────────────────────────────────────────────────────
# Localização do jogo
# ──────────────────────────────────────────────────────────────

# Possíveis nomes de processo / pasta do jogo
GAME_NAME_HINTS = [
    "chaos zero nightmare",
    "chaos_zero",
    "czn",
    "ChaosZero",
    "ChaosZeroNightmare",
]

# Diretórios raiz onde procurar (macOS + Windows)
SEARCH_ROOTS_MACOS = [
    Path.home() / "Library" / "Application Support",
    Path("/Applications"),
    Path.home() / "Documents",
    Path.home() / "Downloads",
    # Steam
    Path.home() / "Library" / "Application Support" / "Steam" / "steamapps" / "common",
    Path("/Volumes"),
]

SEARCH_ROOTS_WINDOWS = [
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
    Path.home() / "AppData" / "LocalLow",
    Path.home() / "AppData" / "Local",
    Path.home() / "AppData" / "Roaming",
    # Steam
    Path("C:/Program Files (x86)/Steam/steamapps/common"),
    Path("C:/Steam/steamapps/common"),
]

# Padrões de arquivo de cache do WebView (Chromium)
CACHE_FILE_NAMES = ["data_2", "data_1", "index"]

# Padrão de URL de API com token (genérico)
# Captura qualquer URL http(s) com parâmetro que pareça token/authkey/uid
URL_PATTERN = re.compile(
    rb"https?://[^\x00-\x1F\x7F \"<>]{30,}(?:authkey|token|uid|gacha|pull|rescue|record)[^\x00-\x1F\x7F \"<>]*",
    re.IGNORECASE,
)

# Padrão mais amplo — qualquer URL longa do jogo
URL_PATTERN_BROAD = re.compile(
    rb"https?://[^\x00-\x1F\x7F \"<>]{50,}",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────
# Busca de arquivos
# ──────────────────────────────────────────────────────────────

def _search_roots() -> list:
    return SEARCH_ROOTS_MACOS if _OS == "Darwin" else SEARCH_ROOTS_WINDOWS


def encontrar_pasta_jogo() -> Optional[Path]:
    """Varre as raízes de instalação procurando a pasta do jogo."""
    print("Procurando a pasta de instalação do jogo...")
    raizes = _search_roots()

    for raiz in raizes:
        if not raiz.exists():
            continue
        try:
            for entry in raiz.iterdir():
                if not entry.is_dir():
                    continue
                nome = entry.name.lower()
                if any(hint.lower() in nome for hint in GAME_NAME_HINTS):
                    print(f"  Encontrado: {entry}")
                    return entry
        except PermissionError:
            continue

    return None


def pedir_pasta_manual() -> Optional[Path]:
    """Pede ao usuário que informe a pasta do jogo manualmente."""
    print()
    print("Pasta do jogo não encontrada automaticamente.")
    print("Por favor, informe o caminho completo da pasta de instalação.")
    print("Exemplo macOS : /Applications/ChaosZeroNightmare.app/Contents")
    print("Exemplo macOS : ~/Library/Application Support/ChaosZeroNightmare")
    print("Exemplo Windows: C:\\Program Files\\ChaosZeroNightmare")
    print()
    caminho = input("Caminho: ").strip().strip('"').strip("'")
    if not caminho:
        return None
    p = Path(caminho).expanduser()
    return p if p.exists() else None


def encontrar_arquivos_cache(pasta: Path) -> list:
    """
    Varre recursivamente a pasta do jogo procurando arquivos de cache
    do WebView (Chromium). Retorna lista de Paths candidatos.
    """
    candidatos = []
    print(f"\nVarrendo cache em: {pasta}")

    # Primeiro: procura pastas "webCaches" ou "Cache" (igual ao HSR)
    for root, dirs, files in os.walk(pasta):
        root_path = Path(root)
        root_lower = root_path.name.lower()

        # Pula pastas irrelevantes grandes
        dirs[:] = [d for d in dirs if d.lower() not in (
            "logs", "resources", "assets", "textures", "shader",
            "audio", "localization", "ui", "art",
        )]

        if any(kw in root_lower for kw in ("webcache", "cache", "webview", "cef")):
            for f in files:
                if f in CACHE_FILE_NAMES or re.match(r"data_\d+", f):
                    candidatos.append(root_path / f)

    if not candidatos:
        # Fallback: qualquer arquivo chamado data_2
        for root, dirs, files in os.walk(pasta):
            dirs[:] = [d for d in dirs if d.lower() not in ("logs", "resources")]
            for f in files:
                if re.match(r"data_\d+", f):
                    candidatos.append(Path(root) / f)

    print(f"  {len(candidatos)} arquivo(s) de cache encontrado(s).")
    return candidatos


# ──────────────────────────────────────────────────────────────
# Extração de URLs
# ──────────────────────────────────────────────────────────────

def extrair_urls(arquivo: Path) -> list:
    """Lê arquivo binário e extrai URLs que pareçam ser de API de pulls."""
    urls = []
    try:
        dados = arquivo.read_bytes()
        # Tenta padrão específico primeiro
        matches = URL_PATTERN.findall(dados)
        if not matches:
            matches = URL_PATTERN_BROAD.findall(dados)

        for m in matches:
            try:
                url = m.decode("utf-8", errors="ignore").strip()
                if url not in urls:
                    urls.append(url)
            except Exception:
                pass
    except (PermissionError, OSError):
        pass
    return urls


def filtrar_urls_relevantes(todas_urls: list) -> list:
    """
    Filtra e pontua URLs por relevância para a API de gacha/pulls.
    Retorna lista ordenada do mais relevante ao menos.
    """
    palavras_chave = [
        "rescue", "gacha", "pull", "record", "history",
        "authkey", "token", "uid", "game_biz",
    ]

    pontuadas = []
    for url in todas_urls:
        url_lower = url.lower()
        pontos = sum(2 if kw in url_lower else 0 for kw in palavras_chave)

        # URLs com parâmetros (query string) são mais prováveis
        if "?" in url and "&" in url:
            pontos += 3

        if pontos > 0:
            pontuadas.append((pontos, url))

    pontuadas.sort(key=lambda x: -x[0])
    return [url for _, url in pontuadas]


# ──────────────────────────────────────────────────────────────
# Teste de API
# ──────────────────────────────────────────────────────────────

def testar_url(url: str, timeout: int = 10) -> Optional[dict]:
    """Faz uma requisição GET para a URL e tenta parsear o JSON de resposta."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            corpo = resp.read().decode("utf-8", errors="ignore")
            return json.loads(corpo)
    except json.JSONDecodeError:
        return {"_raw": corpo[:500]}
    except Exception as exc:
        return {"_erro": str(exc)}


def analisar_resposta(resposta: dict) -> str:
    """Analisa a resposta da API e retorna uma descrição do que foi encontrado."""
    if "_erro" in resposta:
        return f"Erro: {resposta['_erro']}"

    if "_raw" in resposta:
        raw = resposta["_raw"]
        if any(kw in raw.lower() for kw in ("rescue", "pull", "gacha", "record", "history")):
            return "Resposta contém dados de pulls (não é JSON válido — pode ser HTML/outro formato)"
        return f"Resposta não-JSON: {raw[:100]}..."

    # JSON válido — tenta identificar estrutura
    texto = json.dumps(resposta).lower()
    if any(kw in texto for kw in ("rescue_type", "gacha_type", "item_type", "banner")):
        return "DADOS DE PULL ENCONTRADOS!"
    if "list" in resposta and isinstance(resposta.get("list"), list):
        return f"Lista com {len(resposta['list'])} itens"
    if "retcode" in resposta:
        code = resposta.get("retcode")
        msg  = resposta.get("message", "")
        return f"API retornou retcode={code} message='{msg}'"

    return f"JSON genérico: {list(resposta.keys())[:5]}"


# ──────────────────────────────────────────────────────────────
# Download completo do histórico
# ──────────────────────────────────────────────────────────────

def baixar_historico_completo(url_base: str) -> list:
    """
    Dado um endpoint de API que retorna pulls paginados,
    navega por todas as páginas e retorna todos os registros.

    Assume paginação por 'end_id' (padrão HoYoverse).
    Adapte conforme a API real do jogo.
    """
    todos = []
    end_id = "0"
    pagina = 1

    # Parseia URL base para manipular parâmetros
    parsed = urllib.parse.urlparse(url_base)
    params = dict(urllib.parse.parse_qsl(parsed.query))

    print(f"\nBaixando histórico completo via API...")

    while True:
        params["end_id"] = end_id
        nova_query = urllib.parse.urlencode(params)
        nova_url = parsed._replace(query=nova_query).geturl()

        print(f"  Página {pagina} (end_id={end_id})...", end=" ")
        resp = testar_url(nova_url)

        if not resp or "_erro" in resp:
            print(f"Erro: {resp}")
            break

        # Tenta extrair lista de items (adapte conforme estrutura real)
        items = (
            resp.get("data", {}).get("list") or
            resp.get("list") or
            resp.get("records") or
            resp.get("data") if isinstance(resp.get("data"), list) else None
        )

        if items is None:
            print(f"Estrutura desconhecida: {list(resp.keys())}")
            print("  Salve a resposta completa e adapte o parser.")
            break

        if not items:
            print("Última página — sem mais itens.")
            break

        todos.extend(items)
        print(f"{len(items)} item(s). Total: {len(todos)}")

        # Próxima página
        ultimo = items[-1]
        end_id = str(ultimo.get("id") or ultimo.get("pull_id") or "")
        if not end_id:
            print("  Sem ID de paginação — parando.")
            break

        pagina += 1
        time.sleep(0.3)  # respeita rate limit

    return todos


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  Pull Tracker — Leitor de Cache do Jogo")
    print("  (alternativa ao OCR)")
    print("=" * 65)
    print()
    print("IMPORTANTE: Abra o Rescue Records no jogo ANTES de continuar.")
    print("Isso garante que a URL de API ficou registrada no cache.")
    print()
    input("Pressione Enter quando estiver na tela de Rescue Records...")
    print()

    # ── 1. Localizar pasta do jogo ────────────────────────────
    pasta = encontrar_pasta_jogo()
    if not pasta:
        pasta = pedir_pasta_manual()
    if not pasta:
        print("\n[ERRO] Não foi possível localizar a pasta do jogo.")
        print("Verifique se o jogo está instalado e tente novamente.")
        sys.exit(1)

    # ── 2. Encontrar arquivos de cache ────────────────────────
    arquivos = encontrar_arquivos_cache(pasta)
    if not arquivos:
        print("\n[AVISO] Nenhum arquivo de cache encontrado.")
        print("Possíveis causas:")
        print("  • O jogo não usa WebView para o Rescue Records")
        print("  • A pasta informada é incorreta")
        print("  • O cache ainda não foi gerado (abra o Rescue Records no jogo)")
        print()
        print("Neste caso, o método de OCR (run.py) é o caminho disponível.")
        sys.exit(0)

    # ── 3. Extrair URLs ───────────────────────────────────────
    print("\nExtraindo URLs dos arquivos de cache...")
    todas_urls = []
    for arq in arquivos:
        urls = extrair_urls(arq)
        if urls:
            print(f"  {arq.name}: {len(urls)} URL(s)")
            todas_urls.extend(urls)

    if not todas_urls:
        print("\n[AVISO] Nenhuma URL encontrada nos arquivos de cache.")
        print("O jogo pode usar outro mecanismo (ex.: socket, protocolo próprio).")
        print("Método OCR (run.py) continua disponível.")
        sys.exit(0)

    # ── 4. Filtrar e mostrar candidatas ───────────────────────
    relevantes = filtrar_urls_relevantes(todas_urls)

    print(f"\n{len(relevantes)} URL(s) relevante(s) encontrada(s):")
    for i, url in enumerate(relevantes[:10], 1):
        print(f"\n  [{i}] {url[:120]}{'...' if len(url) > 120 else ''}")

    if not relevantes:
        print("\nNenhuma URL parece ser de API de gacha.")
        print("Todas as URLs encontradas:")
        for u in todas_urls[:20]:
            print(f"  {u[:120]}")
        sys.exit(0)

    # ── 5. Testar URLs ────────────────────────────────────────
    print("\n" + "=" * 65)
    print("Testando URLs para confirmar qual retorna dados de pulls...")
    print("=" * 65)

    url_valida = None
    for i, url in enumerate(relevantes[:5], 1):
        print(f"\n[{i}/{min(5, len(relevantes))}] Testando...")
        print(f"  URL: {url[:100]}...")
        resp = testar_url(url)
        descricao = analisar_resposta(resp)
        print(f"  Resultado: {descricao}")

        if "DADOS DE PULL" in descricao or "Lista" in descricao:
            url_valida = url
            print(f"  --> URL VÁLIDA encontrada!")
            break

        time.sleep(0.5)

    # ── 6. Salvar resultado ───────────────────────────────────
    print()
    if url_valida:
        print("=" * 65)
        print("URL de API encontrada com sucesso!")
        print()

        # Salva a URL para uso futuro
        cache_info = {
            "api_url": url_valida,
            "encontrado_em": str(pasta),
            "data_descoberta": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        cache_file = os.path.join(os.path.dirname(__file__), "output", "api_cache.json")
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(cache_info, f, indent=2, ensure_ascii=False)
        print(f"URL salva em: {cache_file}")

        # Pergunta se quer baixar o histórico completo
        print()
        resp_input = input("Baixar o histórico completo agora? (s/n): ").strip().lower()
        if resp_input == "s":
            registros = baixar_historico_completo(url_valida)
            if registros:
                saida = os.path.join(os.path.dirname(__file__), "output", "rescue_data_api.json")
                with open(saida, "w", encoding="utf-8") as f:
                    json.dump({"total": len(registros), "records": registros}, f,
                              indent=2, ensure_ascii=False)
                print(f"\n[OK] {len(registros)} pulls salvos em: {saida}")
            else:
                print("\nNenhum registro obtido.")
    else:
        print("Nenhuma URL de API de pulls foi confirmada.")
        print()
        print("O que isso pode significar:")
        print("  1. O jogo não usa WebView para o Rescue Records")
        print("     → continue usando: python run.py  (OCR)")
        print()
        print("  2. A estrutura da API é diferente do esperado")
        print("     → Inspecione as URLs acima manualmente no navegador")
        print()
        print("  3. O cache ainda não foi gerado")
        print("     → Abra o Rescue Records no jogo e rode este script novamente")

        # Salva todas as URLs para inspeção manual
        saida = os.path.join(os.path.dirname(__file__), "output", "urls_encontradas.txt")
        os.makedirs(os.path.dirname(saida), exist_ok=True)
        with open(saida, "w", encoding="utf-8") as f:
            for url in todas_urls:
                f.write(url + "\n")
        print(f"\nTodas as URLs foram salvas em: {saida}")
        print("Abra este arquivo e verifique se alguma URL parece ser da API de pulls.")


if __name__ == "__main__":
    main()
