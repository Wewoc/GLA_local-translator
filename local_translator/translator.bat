@echo off
setlocal enabledelayedexpansion
title LocalTranslate
echo.
echo  LocalTranslate – Starting...
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Please install Python: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check Docker
:check_docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo  [WARNING] Docker unreachable – LibreTranslate not available.
    echo  Please start Docker Desktop.
    echo.
    echo  [R] Retry   [S] Skip
    set /p docker_choice=Choice: 
    if /i "!docker_choice!"=="r" goto check_docker
    if /i "!docker_choice!"=="s" goto docker_done
    goto check_docker
)
echo  Docker online.
:docker_done
echo.

:: Check Ollama
:check_ollama
curl -s --max-time 3 http://localhost:11434 >nul 2>&1
if errorlevel 1 (
    echo  [WARNING] Ollama unreachable.
    echo  Please start the Ollama Desktop App.
    echo.
    echo  [R] Retry   [S] Skip
    set /p ollama_choice=Choice: 
    if /i "!ollama_choice!"=="r" goto check_ollama
    if /i "!ollama_choice!"=="s" goto ollama_done
    goto check_ollama
)
echo  Ollama online.
:ollama_done
echo.

:: Install dependencies if needed
echo  Checking dependencies...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo  Installing dependencies...
    pip install fastapi uvicorn httpx pyyaml python-dotenv lara-sdk --quiet
)

:: Start LibreTranslate if enabled
findstr /i "libretranslate_enabled: true" config.yaml >nul 2>&1
if not errorlevel 1 (
    echo  LibreTranslate enabled – starting Docker container...
    docker --version >nul 2>&1
    if errorlevel 1 (
        echo  [WARNING] Docker not found – LibreTranslate will not be started.
    ) else (
        set LIBRE_LANGS=
        if exist libretranslate_langs.txt (
            set /p LIBRE_LANGS=<libretranslate_langs.txt
        )
        docker start localtranslate-libre >nul 2>&1
        if errorlevel 1 (
            docker rm -f localtranslate-libre >nul 2>&1
            if "%LIBRE_LANGS%"=="" (
                docker run -d --name localtranslate-libre -p 5000:5000 libretranslate/libretranslate >nul 2>&1
            ) else (
                docker run -d --name localtranslate-libre -p 5000:5000 libretranslate/libretranslate --load-only %LIBRE_LANGS% >nul 2>&1
            )
        )
        echo  LibreTranslate running in background on http://localhost:5000
    )
    echo.
)

:: Start
echo  Starting server...
echo.
python app.py

pause
