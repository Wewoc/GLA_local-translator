#!/bin/bash
echo ""
echo " LocalTranslate – Starting..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo " [ERROR] Python3 not found."
    exit 1
fi

# Install dependencies
echo " Checking dependencies..."
pip3 show fastapi > /dev/null 2>&1 || pip3 install fastapi uvicorn httpx pyyaml python-dotenv lara-sdk --quiet

# LibreTranslate enabled? → ask for opt-in
USE_LIBRE=false
if grep -qi "libretranslate_enabled: true" config.yaml; then
    read -p " Use LibreTranslate (Docker)? [y/N] " libre_choice
    if [[ "$libre_choice" =~ ^[Yy]$ ]]; then
        USE_LIBRE=true
    else
        echo " Skipping LibreTranslate."
    fi
    echo ""
fi

# Check Docker (only if LibreTranslate was requested)
if [ "$USE_LIBRE" = true ]; then
    check_docker() {
        command -v docker &> /dev/null && docker info > /dev/null 2>&1
    }

    while ! check_docker; do
        echo " [WARNING] Docker unreachable – LibreTranslate not available."
        echo " Please start Docker Desktop."
        echo " [R] Retry   [S] Skip"
        read -p " Choice: " docker_choice
        if [[ "$docker_choice" =~ ^[Ss]$ ]]; then
            USE_LIBRE=false
            break
        fi
    done
    if [ "$USE_LIBRE" = true ] && check_docker; then
        echo " Docker online."
    fi
    echo ""
fi

# Check Ollama
check_ollama() {
    curl -s --max-time 3 http://localhost:11434 > /dev/null 2>&1
}

while ! check_ollama; do
    echo " [WARNING] Ollama unreachable. Please start Ollama."
    echo " [R] Retry   [S] Skip"
    read -p " Choice: " ollama_choice
    if [[ "$ollama_choice" =~ ^[Ss]$ ]]; then
        break
    fi
done
if check_ollama; then
    echo " Ollama online."
fi
echo ""

# Start LibreTranslate if enabled and requested
if [ "$USE_LIBRE" = true ]; then
    echo " LibreTranslate enabled – starting Docker container..."
    if ! command -v docker &> /dev/null; then
        echo " [WARNING] Docker not found – LibreTranslate will not be started."
    else
        LIBRE_LANGS=""
        if [ -f libretranslate_langs.txt ]; then
            LIBRE_LANGS=$(cat libretranslate_langs.txt | tr -d '[:space:]')
        fi
        docker start localtranslate-libre > /dev/null 2>&1
        if [ $? -ne 0 ]; then
            docker rm -f localtranslate-libre > /dev/null 2>&1
            if [ -z "$LIBRE_LANGS" ]; then
                docker run -d --name localtranslate-libre -p 5000:5000 libretranslate/libretranslate > /dev/null 2>&1
            else
                docker run -d --name localtranslate-libre -p 5000:5000 libretranslate/libretranslate --load-only "$LIBRE_LANGS" > /dev/null 2>&1
            fi
        fi
        echo " LibreTranslate running in background on http://localhost:5000"
    fi
    echo ""
fi

echo " Starting server..."
echo ""
python3 app.py
