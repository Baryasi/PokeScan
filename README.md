# PokéScan

A small window that floats over your game, reads the Pokémon on screen and shows
how much damage each attacking type does to it, using the type chart of the game
you are playing (Platinum = Gen 4: no Fairy type, Steel resists Ghost and Dark).

**Free by default.** It reads the Pokémon's name off the screen (the battle name box,
"Wild GEODUDE appeared!", "What will PIPLUP do?") with offline text recognition and
looks it up in a built-in Pokédex. No account, no internet, no cost.

Optional **Claude AI (paid)** mode identifies Pokémon from the picture itself (sprites,
nicknamed Pokémon, any screen). It needs an Anthropic API key and costs about 1–2 cents a scan.

## Download (Windows)

Get **PokeScan.exe** from the [latest release](https://github.com/Baryasi/PokeScan/releases/latest)
and double-click it. Nothing to install.

Backup if the release isn't there: download everything in the `dist` folder
(`PokeScan.part1`–`part6` and `join_pieces.bat`) into one folder and double-click
`join_pieces.bat`. GitHub doesn't allow single files over 100 MB, so the .exe is stored in pieces.

## Build PokeScan.exe yourself (Windows)

1. Install Python 3.10+ from python.org (tick "Add python.exe to PATH").
2. Double-click `build_exe.bat` in this folder. It takes a few minutes.
3. Your app is `dist\PokeScan.exe`. It's a single file: copy it anywhere, and it runs
   without Python. You can uninstall Python afterwards if you like.

It only asks for an API key if you tick "Claude AI (paid)". Windows SmartScreen may warn about an unrecognized app the first time;
click "More info" → "Run anyway".

## Run from source instead (any OS)

1. Install Python 3.10+ (on Windows/macOS the python.org installer includes Tk).
2. In this folder run:

       pip install -r requirements.txt

3. Run it.

## Use

    python pokescan.py   (or double-click PokeScan.exe)

- **Game**: pick what you're playing (defaults to Platinum; it remembers your choice).
- **Pick area**: drag a box around your emulator/game window. Without it, the whole main screen is scanned.
- **Scan** or **Ctrl+Shift+P** anywhere: reads the screen once.
- **Auto**: checks every 2.5 s and only rescans when the picture actually changes (new battle, switch-in).
- **Look up**: type a name (even part of it, like "garch") to see its matchups without scanning.

Each card shows FOE first, then your own Pokémon, with rows like
`2× damage: FIRE FIGHTING ROCK STEEL`.

## Notes

- `pokedex.json` is built by `tools/build_pokedex.py` from PokéAPI's CSV files.

- Types are stored offline (from PokéAPI's data) as they were in your game's generation,
  e.g. Togekiss is Normal/Flying in Platinum and Wash Rotom is Electric/Ghost.
- Free mode needs the name to be visible as text. Use Pick area around the game for faster,
  more accurate reads. Alternate forms (Sandy Wormadam, Wash Rotom) look the same as the base
  name on screen, so use Look up for those.
- macOS: allow Screen Recording (and Accessibility for the hotkey) for your terminal in
  System Settings → Privacy & Security.
- Abilities aren't counted (e.g. Levitate makes a Pokémon immune to Ground).
- In Claude AI mode each scan is one API call, about 1–2 cents. Auto mode only calls when the screen changes.
