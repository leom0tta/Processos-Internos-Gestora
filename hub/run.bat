@echo off
title Hub de Processos - Fatorial Capital
cd /d "%~dp0"

echo.
echo  ================================================
echo   Hub de Processos - Fatorial Capital
echo  ================================================
echo.

REM Verifica se Python esta disponivel
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado.
    echo  Instale Python em: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Instala dependencias se necessario
echo  Verificando dependencias...
pip install flask --quiet

echo  Iniciando servidor...
echo  Acesse: http://localhost:5000
echo  Para encerrar: feche esta janela ou pressione Ctrl+C
echo.

python app.py

pause
