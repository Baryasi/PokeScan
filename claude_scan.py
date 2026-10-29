"""Optional paid mode: ask Claude which Pokémon are in a screenshot.

Smarter than the free text reader (works from sprites, nicknames, menus), but each scan
is a billed API call.
"""

import base64
import io
from typing import Literal, Optional

import anthropic
from PIL import Image
from pydantic import BaseModel

from pokedex import DEX, Result, result_for, search
from typechart import TYPES

MODEL = "claude-opus-5-5"
TypeName = Literal[tuple(TYPES)]  # type: ignore[valid-type]


class SeenPokemon(BaseModel):
    name: str
    pokeapi_slug: str
    types: list[TypeName]
    side: Literal["opponent", "player", "other"]
    tera_type: Optional[TypeName]
    confidence: Literal["high", "medium", "low"]


class ScanResult(BaseModel):
    pokemon: list[SeenPokemon]


PROMPT = """This is a screenshot of someone's screen while they play Pokémon {game} \
(Generation {gen}), likely on an emulator or console capture. It could also be a Pokédex, \
summary screen, menu or party screen from that game.

List every distinct Pokémon you can identify on screen. For each one:
- name: the display name, including regional/alternate form (e.g. "Alolan Raichu", "Mega Charizard X").
- pokeapi_slug: its PokéAPI identifier, lowercase and hyphenated (e.g. "raichu-alola", \
"charizard-mega-x", "urshifu-rapid-strike", "mr-mime"). Use the default form's slug when the form is normal.
- types: its types (1 or 2) as they were in Generation {gen}, lowercase (e.g. no Fairy type before Gen 6).
- side: "opponent" for the foe in a battle, "player" for the user's own battling Pokémon, otherwise "other".
- tera_type: only if the Pokémon is visibly Terastallized (crystal look / tera icon) and you can tell the tera type; else null.
- confidence: how sure you are of the identification.

Use on-screen text (name boxes, nicknames are not species though) and the sprite/model together. \
If no Pokémon is visible, return an empty list."""

_client: anthropic.Anthropic | None = None


def set_api_key(key: str) -> None:
    global _client
    _client = anthropic.Anthropic(api_key=key)


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def encode_image(img: Image.Image, max_edge: int = 1568) -> str:
    img = img.convert("RGB")
    scale = max_edge / max(img.size)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def scan(img: Image.Image, game: str, gen: int) -> list[Result]:
    response = _get_client().messages.parse(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        output_format=ScanResult,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": encode_image(img)}},
                {"type": "text", "text": PROMPT.format(game=game, gen=gen)},
            ],
        }],
        # Server-side fallback: if a safety classifier declines, retry on another model automatically.
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to read this screenshot.")
    if response.parsed_output is None:
        raise RuntimeError(f"Couldn't read Claude's answer (stop reason: {response.stop_reason}).")
    return [_to_result(p, gen) for p in response.parsed_output.pokemon]


def _to_result(p: SeenPokemon, gen: int) -> Result:
    note = "" if p.confidence == "high" else f"{p.confidence} confidence"
    if p.tera_type and gen >= 9:
        return Result(p.name, p.side, [p.tera_type], "Claude · Terastallized", note)
    slug = p.pokeapi_slug.strip().lower()
    if slug not in DEX:
        slug = search(p.name, gen)
    if slug:
        r = result_for(slug, gen, p.side, "Claude", note)
        r.name = p.name
        return r
    return Result(p.name, p.side, [t for t in p.types if t != "fairy" or gen >= 6] or ["normal"], "Claude", note)
