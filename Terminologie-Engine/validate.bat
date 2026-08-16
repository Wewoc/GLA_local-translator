@echo off
title Terminologie-Engine — Validation
echo.
echo  Terminologie-Engine — Pass 3 translation validation
echo  Model: aya-expanse:latest
echo.

cd /d "%~dp0"

python filter_terminology.py --dir "..\terminology" --validate --model aya-expanse:latest

echo.
pause
