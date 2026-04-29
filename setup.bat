@echo off
chcp 65001 >nul
echo ============================================================
echo  Pull Tracker — Chaos Zero Nightmare
echo  Instalacao de dependencias
echo ============================================================
echo.

:: Verifica se Python esta instalado
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado!
    echo.
    echo Instale o Python 3.10 ou superior em:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: Na instalacao, marque a opcao "Add Python to PATH"
    pause
    exit /b 1
)

echo [OK] Python encontrado:
python --version
echo.

:: Instala dependencias
echo Instalando dependencias Python...
echo.
pip install -r requirements.txt

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Falha ao instalar dependencias.
    echo Tente rodar manualmente: pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [OK] Dependencias instaladas com sucesso!
echo.
echo PROXIMO PASSO: Instale o Tesseract OCR (se ainda nao instalou)
echo   https://github.com/UB-Mannheim/tesseract/wiki
echo   Instale no caminho padrao: C:\Program Files\Tesseract-OCR\
echo.
echo Depois rode: python verificar_setup.py
echo ============================================================
echo.
pause
