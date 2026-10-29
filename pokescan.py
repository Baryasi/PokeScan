"""PokéScan: a floating window that reads the Pokémon on your screen and shows its weaknesses.

Free by default: it reads names off the screen with offline text recognition.
Optionally, Claude can identify Pokémon from the picture instead (paid, needs an API key).

Run:  python pokescan.py
Keys: Ctrl+Shift+P scans from anywhere (needs pynput).
"""

import json
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path

if sys.platform == "win32":
    # Make Tk and the screen grabber agree on pixel coordinates on scaled displays.
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

import mss

_MSS = getattr(mss, "MSS", None) or mss.mss  # newer mss renamed the class
from PIL import Image, ImageChops, ImageStat

import anthropic

import claude_scan
import ocr_scan
from pokedex import result_for, search
from typechart import DEFAULT_GAME, GAMES, TYPE_COLORS, defensive_profile

BG, PANEL, FG, MUTED, ACCENT = "#16181d", "#20232a", "#eef0f4", "#8b919e", "#ffcb05"
AUTO_INTERVAL_MS = 2500
CHANGE_THRESHOLD = 6.0  # mean pixel difference (0-255) that counts as "the screen changed"

ROWS = [
    (4, "4× damage"), (2, "2× damage"), (0.5, "½× damage"), (0.25, "¼× damage"), (0, "0× (immune)"),
]
GEN_OF = dict(GAMES)
SETTINGS_PATH = Path.home() / ".pokescan_settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except (OSError, ValueError):
        return {}


def save_setting(key: str, value) -> None:
    settings = load_settings()
    settings[key] = value
    try:
        SETTINGS_PATH.write_text(json.dumps(settings))
    except OSError:
        pass


class RegionPicker(tk.Toplevel):
    """Full-screen dimmed overlay; drag a box to choose what gets scanned."""

    def __init__(self, master, on_pick):
        super().__init__(master)
        self.on_pick = on_pick
        with _MSS() as sct:
            mon = sct.monitors[0]
        self.ox, self.oy = mon["left"], mon["top"]
        self.overrideredirect(True)
        self.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.3)
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(mon["width"] // 2, 60, text="Drag around the game. Esc to cancel.",
                                fill="white", font=("Segoe UI", 20, "bold"))
        self.start = None
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        self.bind("<Escape>", lambda e: self.destroy())
        self.focus_force()

    def _down(self, e):
        self.start = (e.x, e.y)
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline=ACCENT, width=3)

    def _drag(self, e):
        if self.rect:
            self.canvas.coords(self.rect, *self.start, e.x, e.y)

    def _up(self, e):
        x0, y0 = self.start
        x1, y1 = e.x, e.y
        self.destroy()
        if abs(x1 - x0) > 20 and abs(y1 - y0) > 20:
            self.on_pick({
                "left": self.ox + min(x0, x1), "top": self.oy + min(y0, y1),
                "width": abs(x1 - x0), "height": abs(y1 - y0),
            })


class PokeScan(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PokéScan")
        self.configure(bg=BG)
        self.attributes("-topmost", True)
        self.geometry("380x520+40+40")
        self.minsize(320, 300)

        self.region = None          # None = primary monitor
        self.busy = False
        self.last_scanned = None    # thumbnail of the last frame scanned
        self.results = queue.Queue()
        self.auto = tk.BooleanVar(value=False)
        settings = load_settings()
        game = settings.get("game")
        self.game = tk.StringVar(value=game if game in GEN_OF else DEFAULT_GAME)
        self.use_claude = tk.BooleanVar(value=settings.get("engine") == "claude")
        self.has_key = False

        key = os.environ.get("ANTHROPIC_API_KEY") or settings.get("api_key")
        if key:
            claude_scan.set_api_key(key)
            self.has_key = True

        self._build_ui()
        self.capture_safe = False
        self.after(300, lambda: setattr(self, "capture_safe", self._exclude_from_capture()))
        self._start_hotkey()
        self.after(100, self._poll_results)
        threading.Thread(target=ocr_scan.warm_up, daemon=True).start()

    # --- UI -------------------------------------------------------------------

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=(12, 6))
        self._button(bar, "Scan", self.scan, primary=True).pack(side="left")
        self._button(bar, "Pick area", self.pick_region).pack(side="left", padx=6)
        tk.Checkbutton(bar, text="Auto", variable=self.auto, command=self._auto_toggled,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                       activeforeground=FG, font=("Segoe UI", 10)).pack(side="left")

        gamebar = tk.Frame(self, bg=BG)
        gamebar.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(gamebar, text="Game", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        menu = tk.OptionMenu(gamebar, self.game, *[g for g, _ in GAMES], command=self._game_changed)
        menu.config(bg=PANEL, fg=FG, activebackground=PANEL, activeforeground=FG, relief="flat",
                    highlightthickness=0, font=("Segoe UI", 9))
        menu["menu"].config(bg=PANEL, fg=FG)
        menu.pack(side="left", padx=6)
        self.gen_label = tk.Label(gamebar, bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.gen_label.pack(side="left")
        self._game_changed(self.game.get())

        searchbar = tk.Frame(self, bg=BG)
        searchbar.pack(fill="x", padx=12, pady=(0, 6))
        self.search_entry = tk.Entry(searchbar, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                                     font=("Segoe UI", 10))
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.search_entry.bind("<Return>", self._search)
        self._button(searchbar, "Look up", self._search).pack(side="left", padx=(6, 0))
        tk.Checkbutton(bar, text="Claude AI (paid)", variable=self.use_claude,
                       command=self._engine_toggled, bg=BG, fg=MUTED, selectcolor=PANEL,
                       activebackground=BG, activeforeground=FG, font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))

        self.status = tk.Label(self, text="Whole screen · press Scan or Ctrl+Shift+P",
                               bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.status.pack(fill="x", padx=12)

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=12, pady=8)

    @property
    def gen(self) -> int:
        return GEN_OF[self.game.get()]

    def _game_changed(self, game):
        self.gen_label.config(text=f"Gen {GEN_OF[game]} type chart")
        self.last_scanned = None
        save_setting("game", game)

    def _engine_toggled(self):
        claude = self.use_claude.get()
        save_setting("engine", "claude" if claude else "free")
        self.last_scanned = None
        if claude and not self.has_key:
            self._ask_for_key()
        elif not claude:
            self._set_status("Free mode: reads Pokémon names on screen")

    def _search(self, _event=None):
        slug = search(self.search_entry.get(), self.gen)
        if slug is None:
            self._set_status(f"No Pokémon in {self.game.get()} called \"{self.search_entry.get()}\"")
            return
        self._render([result_for(slug, self.gen, source="search")], self.gen)
        self._set_status("Looked up by name")

    def _ask_for_key(self, message="Claude AI mode needs an Anthropic API key. Each scan costs about 1–2 cents."):
        """Shows the API key form in place of the results."""
        for w in self.body.winfo_children():
            w.destroy()
        box = tk.Frame(self.body, bg=PANEL, padx=10, pady=10)
        box.pack(fill="x")
        tk.Label(box, text=message, bg=PANEL, fg=FG, font=("Segoe UI", 10), wraplength=320,
                 justify="left").pack(anchor="w")
        tk.Label(box, text="Get one at console.anthropic.com → API keys. It's saved on this PC only.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8), wraplength=320, justify="left").pack(anchor="w", pady=(2, 6))
        entry = tk.Entry(box, show="•", bg=BG, fg=FG, insertbackground=FG, relief="flat",
                         font=("Segoe UI", 10))
        entry.pack(fill="x", ipady=4)
        entry.focus_set()

        def save(_event=None):
            key = entry.get().strip()
            if not key:
                return
            claude_scan.set_api_key(key)
            self.has_key = True
            save_setting("api_key", key)
            for w in self.body.winfo_children():
                w.destroy()
            self._set_status("Key saved · press Scan or Ctrl+Shift+P")

        def cancel():
            self.use_claude.set(False)
            self._engine_toggled()
            for w in self.body.winfo_children():
                w.destroy()

        entry.bind("<Return>", save)
        buttons = tk.Frame(box, bg=PANEL)
        buttons.pack(anchor="w", pady=(8, 0))
        self._button(buttons, "Save key", save, primary=True).pack(side="left")
        self._button(buttons, "Use free mode", cancel).pack(side="left", padx=6)

    def _button(self, parent, text, cmd, primary=False):
        return tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, padx=12, pady=5,
                         bg=ACCENT if primary else PANEL, fg="#111" if primary else FG,
                         activebackground=ACCENT, font=("Segoe UI", 10, "bold"))

    def _badge(self, parent, t, small=False):
        return tk.Label(parent, text=t.upper(), bg=TYPE_COLORS[t], fg="white",
                        font=("Segoe UI", 8 if small else 9, "bold"), padx=6, pady=1)

    def _set_status(self, text):
        self.status.config(text=text)

    def _render(self, results, gen):
        for w in self.body.winfo_children():
            w.destroy()
        order = {"opponent": 0, "other": 1, "player": 2}
        for r in sorted(results, key=lambda r: order[r.side]):
            self._card(r, gen)

    def _card(self, p, gen):
        types = p.types
        card = tk.Frame(self.body, bg=PANEL, padx=10, pady=8)
        card.pack(fill="x", pady=(0, 8))

        head = tk.Frame(card, bg=PANEL)
        head.pack(fill="x")
        label = {"opponent": "FOE", "player": "YOURS", "other": ""}[p.side]
        if label:
            tk.Label(head, text=label, bg=PANEL, fg=ACCENT, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))
        tk.Label(head, text=p.name, bg=PANEL, fg=FG, font=("Segoe UI", 13, "bold")).pack(side="left")
        for t in types:
            self._badge(head, t).pack(side="left", padx=(6, 0))

        note = f"Gen {gen} types · {p.source}" + (f" · {p.note}" if p.note else "")
        tk.Label(card, text=note, bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 4))

        tk.Label(card, text="Moves of these types do:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")
        profile = defensive_profile(types, gen)
        for mult, title in ROWS:
            atk = profile[mult]
            if not atk:
                continue
            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x", pady=2)
            strong = mult >= 2
            tk.Label(row, text=title, width=11, anchor="w", bg=PANEL,
                     fg="#ff6b6b" if strong else MUTED,
                     font=("Segoe UI", 9, "bold" if strong else "normal")).pack(side="left")
            wrap = tk.Frame(row, bg=PANEL)
            wrap.pack(side="left", fill="x", expand=True)
            for i, t in enumerate(atk):
                self._badge(wrap, t, small=not strong).grid(row=i // 5, column=i % 5, padx=2, pady=1, sticky="w")

    # --- Capture & scan ------------------------------------------------------

    def pick_region(self):
        def picked(region):
            self.region = region
            self.last_scanned = None
            self._set_status(f"Area {region['width']}×{region['height']} · press Scan")
        RegionPicker(self, picked)

    def _exclude_from_capture(self) -> bool:
        """Asks Windows to leave this window out of screenshots (Windows 10 2004+)."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            WDA_EXCLUDEFROMCAPTURE = 0x11
            return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
        except Exception:
            return False

    def _overlaps(self, area) -> bool:
        x, y = self.winfo_rootx(), self.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        return not (x + w <= area["left"] or area["left"] + area["width"] <= x or
                    y + h <= area["top"] or area["top"] + area["height"] <= y)

    def _grab(self) -> Image.Image:
        with _MSS() as sct:
            area = self.region or sct.monitors[1]
            # Only when Windows can't leave us out of the screenshot and we're in the way:
            # hide for a moment so we don't scan ourselves (this is what causes a flicker).
            hide = not self.capture_safe and self._overlaps(area)
            if hide:
                self.attributes("-alpha", 0.0)
                self.update()
            try:
                shot = sct.grab(area)
            finally:
                if hide:
                    self.attributes("-alpha", 1.0)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    @staticmethod
    def _thumb(img):
        return img.convert("L").resize((64, 36))

    def scan(self, img=None):
        if self.busy:
            return
        if img is None:
            img = self._grab()
        self.busy = True
        self.last_scanned = self._thumb(img)
        self._set_status("Looking…")
        game, gen = self.game.get(), self.gen
        claude = self.use_claude.get() and self.has_key
        threading.Thread(target=self._scan_worker, args=(img, game, gen, claude), daemon=True).start()

    def _scan_worker(self, img, game, gen, claude):
        try:
            found = claude_scan.scan(img, game, gen) if claude else ocr_scan.scan(img, gen)
            self.results.put(("ok", (found, gen)))
        except anthropic.AuthenticationError:
            self.results.put(("bad_key", None))
        except Exception as e:  # shown in the window, scanning keeps working
            self.results.put(("error", str(e)))

    def _poll_results(self):
        try:
            kind, payload = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            if kind == "ok":
                found, gen = payload
                self._render(found, gen)
                if found:
                    self._set_status("Saw " + ", ".join(r.name for r in found))
                else:
                    self._set_status("No Pokémon on screen")
            elif kind == "bad_key":
                self.has_key = False
                self._set_status("Scan failed: API key was rejected")
                self._ask_for_key("That API key didn't work. Paste a valid one.")
            else:
                self._set_status(f"Scan failed: {payload}")
        self.after(100, self._poll_results)

    # --- Auto mode: rescan only when the picture actually changes ----------

    def _auto_toggled(self):
        if self.auto.get():
            self._auto_tick()

    def _auto_tick(self):
        if not self.auto.get():
            return
        if not self.busy:
            img = self._grab()
            thumb = self._thumb(img)
            if self.last_scanned is None or \
                    ImageStat.Stat(ImageChops.difference(thumb, self.last_scanned)).mean[0] > CHANGE_THRESHOLD:
                self.scan(img)
        self.after(AUTO_INTERVAL_MS, self._auto_tick)

    # --- Global hotkey --------------------------------------------------------

    def _start_hotkey(self):
        try:
            from pynput import keyboard
        except ImportError:
            return
        hk = keyboard.GlobalHotKeys({"<ctrl>+<shift>+p": lambda: self.after(0, self.scan)})
        hk.daemon = True
        hk.start()


if __name__ == "__main__":
    PokeScan().mainloop()
