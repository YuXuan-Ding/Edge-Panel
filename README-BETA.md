# Edge Panel — Beta (Non-Tech Version)

A desktop edge panel that slides out from the side of your screen for quick AI Q&A.

## For End Users (no Python needed)

1. Download `EdgePanel.exe` from the [Releases page](https://github.com/YuXuan-Ding/Edge-Panel/releases).
2. Double-click to run. (Windows Defender may warn — see "Antivirus warnings" below.)
3. Push your mouse to the right edge of your screen, or press **Alt + Space**, to open the panel.
4. Click **⚙ Settings** to add an API key (free Gemini key at [aistudio.google.com](https://aistudio.google.com/apikey)).
5. Type a question and press Enter.

### Controls

| Action | How |
|---|---|
| Open panel | Hover the right edge OR press Alt+Space |
| Type question | Just type — input auto-focuses |
| Submit | Enter (Shift+Enter = new line) |
| Pin (keep open) | Click ⌖ button or anywhere on the panel chrome |
| Unpin | Click ⌖ again, press Esc, or click without selecting |
| Drag panel | Click+drag the top bar; snap back to either screen edge |
| Attach image | Ctrl+V to paste an image into the input |
| Clear chat | Click the ↻ button |
| Quit program | Click the ✕ button |

### Antivirus warnings

Some antivirus tools flag PyInstaller-built `.exe` files as suspicious. This is a known false positive — the build process is described in `build.bat` and is fully open source on this repo. If you don't trust the binary, build it yourself from source (see "For Developers" below).

### Where settings live

`%USERPROFILE%\.edge_panel\config.json` (typically `C:\Users\YOU\.edge_panel\config.json`). API keys are stored in plain text here. Delete the folder to reset all settings.

---

## For Developers (build from source)

Requirements: Python 3.10+, Windows.

```powershell
git clone https://github.com/YuXuan-Ding/Edge-Panel.git
cd Edge-Panel
git checkout beta
pip install -r requirements.txt
pip install -r requirements-dev.txt
build.bat
```

Output: `dist\EdgePanel.exe` (one self-contained file, ~150MB).
