@echo off
setlocal
echo ============================================
echo  Build: Pull Tracker GUI
echo ============================================
echo.

:: Instala dependencias se necessario
pip install customtkinter pyinstaller --quiet

echo Gerando executavel (isso pode levar alguns minutos)...
echo.

pyinstaller ^
  --onefile ^
  --windowed ^
  --name "PullTracker" ^
  --icon "icon.ico" ^
  --collect-all customtkinter ^
  --add-data "rescue_tracker\characters.json;rescue_tracker" ^
  --manifest "PullTracker.manifest" ^
  gui.py

echo.
if exist "dist\PullTracker.exe" (
    echo  Sucesso! Executavel gerado em:
    echo  dist\PullTracker.exe
) else (
    echo  ERRO: Falha ao gerar o executavel.
    echo  Verifique se o pyinstaller esta instalado corretamente.
)
echo.
pause
