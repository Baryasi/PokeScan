"""Gen 6+ type effectiveness chart and defensive matchup math."""

TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison",
    "ground", "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark",
    "steel", "fairy",
]

# CHART[attacking][defending] -> multiplier; anything missing is 1x.
CHART = {
    "normal":   {"rock": .5, "ghost": 0, "steel": .5},
    "fire":     {"fire": .5, "water": .5, "grass": 2, "ice": 2, "bug": 2, "rock": .5, "dragon": .5, "steel": 2},
    "water":    {"fire": 2, "water": .5, "grass": .5, "ground": 2, "rock": 2, "dragon": .5},
    "electric": {"water": 2, "electric": .5, "grass": .5, "ground": 0, "flying": 2, "dragon": .5},
    "grass":    {"fire": .5, "water": 2, "grass": .5, "poison": .5, "ground": 2, "flying": .5, "bug": .5, "rock": 2, "dragon": .5, "steel": .5},
    "ice":      {"fire": .5, "water": .5, "grass": 2, "ice": .5, "ground": 2, "flying": 2, "dragon": 2, "steel": .5},
    "fighting": {"normal": 2, "ice": 2, "poison": .5, "flying": .5, "psychic": .5, "bug": .5, "rock": 2, "ghost": 0, "dark": 2, "steel": 2, "fairy": .5},
    "poison":   {"grass": 2, "poison": .5, "ground": .5, "rock": .5, "ghost": .5, "steel": 0, "fairy": 2},
    "ground":   {"fire": 2, "electric": 2, "grass": .5, "poison": 2, "flying": 0, "bug": .5, "rock": 2, "steel": 2},
    "flying":   {"electric": .5, "grass": 2, "fighting": 2, "bug": 2, "rock": .5, "steel": .5},
    "psychic":  {"fighting": 2, "poison": 2, "psychic": .5, "dark": 0, "steel": .5},
    "bug":      {"fire": .5, "grass": 2, "fighting": .5, "poison": .5, "flying": .5, "psychic": 2, "ghost": .5, "dark": 2, "steel": .5, "fairy": .5},
    "rock":     {"fire": 2, "ice": 2, "fighting": .5, "ground": .5, "flying": 2, "bug": 2, "steel": .5},
    "ghost":    {"normal": 0, "psychic": 2, "ghost": 2, "dark": .5},
    "dragon":   {"dragon": 2, "steel": .5, "fairy": 0},
    "dark":     {"fighting": .5, "psychic": 2, "ghost": 2, "dark": .5, "fairy": .5},
    "steel":    {"fire": .5, "water": .5, "electric": .5, "ice": 2, "rock": 2, "steel": .5, "fairy": 2},
    "fairy":    {"fire": .5, "fighting": 2, "poison": .5, "dragon": 2, "dark": 2, "steel": .5},
}

TYPE_COLORS = {
    "normal": "#9fa19f", "fire": "#e62829", "water": "#2980ef", "electric": "#fac000",
    "grass": "#3fa129", "ice": "#3dcef3", "fighting": "#ff8000", "poison": "#9141cb",
    "ground": "#915121", "flying": "#81b9ef", "psychic": "#ef4179", "bug": "#91a119",
    "rock": "#afa981", "ghost": "#704170", "dragon": "#5060e1", "dark": "#624d4e",
    "steel": "#60a1b8", "fairy": "#ef70ef",
}


# Games you can pick, newest first, with their generation.
GAMES = [
    ("Scarlet / Violet", 9), ("Legends: Arceus", 8), ("Brilliant Diamond / Shining Pearl", 8),
    ("Sword / Shield", 8), ("Let's Go Pikachu / Eevee", 7), ("Ultra Sun / Ultra Moon", 7),
    ("Sun / Moon", 7), ("Omega Ruby / Alpha Sapphire", 6), ("X / Y", 6),
    ("Black 2 / White 2", 5), ("Black / White", 5), ("HeartGold / SoulSilver", 4),
    ("Platinum", 4), ("Diamond / Pearl", 4), ("FireRed / LeafGreen", 3), ("Emerald", 3),
    ("Ruby / Sapphire", 3), ("Gold / Silver / Crystal", 2), ("Red / Blue / Yellow", 1),
]
DEFAULT_GAME = "Platinum"


def types_for_gen(gen: int) -> list[str]:
    drop = {"fairy"} if gen < 6 else set()
    if gen == 1:
        drop |= {"dark", "steel"}
    return [t for t in TYPES if t not in drop]


def chart_for_gen(gen: int) -> dict[str, dict[str, float]]:
    """The type chart as it was in a given generation."""
    chart = {atk: dict(row) for atk, row in CHART.items()}
    if gen < 6:
        # Before Fairy existed, Steel also resisted Ghost and Dark.
        chart["ghost"]["steel"] = .5
        chart["dark"]["steel"] = .5
    if gen == 1:
        chart["ghost"]["psychic"] = 0      # the famous Gen 1 bug
        chart["bug"]["poison"] = 2
        chart["poison"]["bug"] = 2
        chart["ice"].pop("fire", None)     # Fire didn't resist Ice yet
    valid = set(types_for_gen(gen))
    return {atk: {d: m for d, m in row.items() if d in valid}
            for atk, row in chart.items() if atk in valid}


def multiplier(attacking: str, defending: list[str], gen: int = 9) -> float:
    chart = chart_for_gen(gen)
    m = 1.0
    for d in defending:
        m *= chart[attacking].get(d, 1)
    return m


def defensive_profile(defending: list[str], gen: int = 9) -> dict[float, list[str]]:
    """Group attacking types by how much damage they deal to this type combo in that generation."""
    groups: dict[float, list[str]] = {4: [], 2: [], 0.5: [], 0.25: [], 0: []}
    for atk in types_for_gen(gen):
        m = multiplier(atk, defending, gen)
        if m in groups:
            groups[m].append(atk)
    return groups
