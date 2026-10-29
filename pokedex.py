"""Offline Pokédex: names, per-generation types and fuzzy name matching."""

import difflib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class Result:
    """One Pokémon to show a card for."""
    name: str
    side: str          # "opponent", "player" or "other"
    types: list[str]
    source: str        # where the types came from, shown under the name
    note: str = ""


def _resource(name: str) -> Path:
    # Inside the .exe, bundled files live in a temp folder PyInstaller sets up.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / name


DEX: dict[str, dict] = json.loads(_resource("pokedex.json").read_text(encoding="utf-8"))


def types_in_gen(slug: str, gen: int) -> list[str]:
    entry = DEX[slug]
    for until_gen, types in entry["past"]:
        if gen <= until_gen:
            return types
    return entry["types"]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", text.lower())


@lru_cache(maxsize=None)
def _species_index(gen: int) -> dict[str, str]:
    """Normalized species name -> slug, for species that exist in that generation."""
    return {normalize(e["name"]): slug for slug, e in DEX.items() if e["default"] and e["gen"] <= gen}


@lru_cache(maxsize=None)
def _all_index(gen: int) -> dict[str, str]:
    """Like _species_index but also alternate forms (Wash Rotom, Sandy Wormadam...)."""
    index = {normalize(e["name"]): slug for slug, e in DEX.items() if e["gen"] <= gen}
    index.update({normalize(slug): slug for slug, e in DEX.items() if e["gen"] <= gen})
    index.update(_species_index(gen))
    return index


def _match(word: str, index: dict[str, str]) -> str | None:
    if word in index:
        return index[word]
    # Short names (Mew, Muk, Onix) must match exactly or ordinary words get mistaken for them.
    if len(word) < 5:
        return None
    close = difflib.get_close_matches(word, index.keys(), n=1, cutoff=0.84)
    return index[close[0]] if close else None


def find_in_text(text: str, gen: int) -> list[str]:
    """Species slugs named in a line of on-screen text, tolerating OCR mistakes."""
    index = _species_index(gen)
    words = [normalize(w) for w in re.findall(r"[^\W\d_][^\s]*", text)]
    words = [w for w in words if w]
    found = []
    i = 0
    while i < len(words):
        # Try two-word names first (Mr. Mime, Mime Jr., Tapu Koko).
        pair = words[i] + words[i + 1] if i + 1 < len(words) else None
        if pair and pair in index:
            found.append(index[pair])
            i += 2
            continue
        slug = _match(words[i], index)
        if slug:
            found.append(slug)
        i += 1
    return found


def search(query: str, gen: int) -> str | None:
    """Best slug for a typed name (forms included), or None."""
    word = normalize(query)
    if not word:
        return None
    index = _all_index(gen)
    if word in index:
        return index[word]
    starts = sorted(k for k in index if k.startswith(word))
    if starts:
        return index[starts[0]]
    close = difflib.get_close_matches(word, index.keys(), n=1, cutoff=0.6)
    return index[close[0]] if close else None


def result_for(slug: str, gen: int, side: str = "other", source: str = "", note: str = "") -> Result:
    return Result(DEX[slug]["name"], side, types_in_gen(slug, gen), source, note)
