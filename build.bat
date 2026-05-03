@echo off
REM Build EdgePanel.exe for end users.
REM Requires: pip install -r requirements.txt && pip install -r requirements-dev.txt

echo === Cleaning previous build ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist EdgePanel.spec del EdgePanel.spec

echo === Running PyInstaller ===
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name EdgePanel ^
    --hidden-import=anthropic ^
    --hidden-import=openai ^
    --hidden-import=google.genai ^
    --hidden-import=google.genai.types ^
    --hidden-import=pynput.keyboard ^
    --hidden-import=pynput.mouse ^
    --collect-submodules=pynput ^
    main.py

if exist dist\EdgePanel.exe (
    echo.
    echo === Build successful ===
    echo Executable: dist\EdgePanel.exe
    dir dist\EdgePanel.exe | findstr EdgePanel.exe
) else (
    echo.
    echo === Build FAILED ===
    exit /b 1
)
