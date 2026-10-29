"""Free, offline scanning: read the text on screen and look for Pokémon names in it."""

import re
import threading

import numpy as np
from PIL import Image

from pokedex import Result, find_in_text, result_for

_engine = None
_engine_lock = threading.Lock()


def _get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        return _engine


def warm_up() -> None:
    """Loads the OCR model ahead of the first scan (it takes a second or two)."""
    _get_engine()


def read_lines(img: Image.Image) -> list[tuple[str, float, float]]:
    """(text, x centre, y centre) for every line of text found; positions are 0..1 of the image."""
    img = img.convert("RGB")
    # Small captures (a DS screen at 1x) read much better scaled up with hard pixel edges.
    if img.width < 900:
        factor = max(2, 900 // img.width)
        img = img.resize((img.width * factor, img.height * factor), Image.NEAREST)
    result, _ = _get_engine()(np.array(img))
    lines = []
    for box, text, _score in result or []:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        lines.append((text, (min(xs) + max(xs)) / 2 / img.width, (min(ys) + max(ys)) / 2 / img.height))
    return lines


# The level next to a name: "Lv14", and how OCR tends to misread the games' stylized
# Lv glyph ("Lw23", "Lu23", "1v23"), plus "Nv."/"N." used by Spanish/Italian/French games.
# The gender sign in front often comes out as a letter ("QLw23"), so the longer forms may follow one.
LEVEL = re.compile(r"((lv|lw|lu|iv|1v|nv|niv)|\b[ln])\s?\.?\s?\d{1,3}(?!\d)", re.IGNORECASE)
# "What will PIPLUP do?" in the languages the games ship in.
PLAYER_PROMPT = re.compile(
    r"what will|deber[ií]a hacer|que doit faire|was soll|cosa deve fare|che cosa deve", re.IGNORECASE)
FOE_WORDS = re.compile(
    r"\b(foe|wild|opposing|salvaje|enemigo|sauvage|ennemi|wilde?s?|selvatico|nemico)\b", re.IGNORECASE)


def _box_sides(boxes: list[tuple[str, float, float]]) -> dict[str, str]:
    """Which battle name boxes are the foe's: they sit above (and left of) yours."""
    if not boxes:
        return {}
    if len(boxes) == 1:
        slug, x, _y = boxes[0]
        return {slug: "opponent" if x < 0.5 else "player"}
    top = min(y for _, _, y in boxes)
    bottom = max(y for _, _, y in boxes)
    if bottom - top < 0.03:  # all on one row: fall back to left/right
        return {slug: "opponent" if x < 0.5 else "player" for slug, x, _ in boxes}
    middle = (top + bottom) / 2
    return {slug: "opponent" if y < middle else "player" for slug, _, y in boxes}


def scan(img: Image.Image, gen: int) -> list[Result]:
    lines = read_lines(img)
    # OCR often splits "STARAVIA  Lv14" into two pieces; a level on the same row marks a name box.
    level_rows = [y for text, _, y in lines if LEVEL.search(text)]
    order: list[str] = []
    prompted, foes, boxes = set(), set(), []
    for text, x, y in lines:
        slugs = find_in_text(text, gen)
        order += [s for s in slugs if s not in order]
        if PLAYER_PROMPT.search(text):
            prompted.update(slugs)
        elif FOE_WORDS.search(text):
            foes.update(slugs)
        elif LEVEL.search(text) or any(abs(y - ly) < 0.03 for ly in level_rows):
            boxes += [(s, x, y) for s in slugs]

    box_side = _box_sides(boxes)
    # If the prompt names your Pokémon, every other name box is a foe.
    if prompted and len(boxes) > 1:
        box_side = {slug: "player" if slug in prompted else "opponent" for slug, _, _ in boxes}

    def side(slug: str) -> str:
        if slug in prompted:
            return "player"
        if slug in foes:
            return "opponent"
        return box_side.get(slug, "other")

    return [result_for(slug, gen, side(slug), "read from screen") for slug in order]
