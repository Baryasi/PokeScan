"""Builds pokedex.json from PokéAPI's CSV dump, so the app needs no internet for lookups.

Usage: python tools/build_pokedex.py <folder with PokéAPI csv files> pokedex.json
CSVs: https://github.com/PokeAPI/pokeapi/tree/master/data/v2/csv
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ENGLISH = "9"
SKIP = ("-totem", "-gmax", "-cap", "-starter", "-cosplay", "-rock-star", "-belle", "-pop-star",
        "-phd", "-libre", "-busted", "-eternamax")


def rows(folder: Path, name: str):
    with open(folder / f"{name}.csv", newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def main(folder: Path, out: Path):
    type_name = {r["id"]: r["identifier"] for r in rows(folder, "types")}
    vg_gen = {r["id"]: int(r["generation_id"]) for r in rows(folder, "version_groups")}
    species = {r["id"]: r for r in rows(folder, "pokemon_species")}
    species_name = {r["pokemon_species_id"]: r["name"] for r in rows(folder, "pokemon_species_names")
                    if r["local_language_id"] == ENGLISH}

    form_of = {}  # pokemon id -> its default form row
    for r in rows(folder, "pokemon_forms"):
        if r["is_default"] == "1":
            form_of[r["pokemon_id"]] = r
    form_name = {r["pokemon_form_id"]: r["pokemon_name"] for r in rows(folder, "pokemon_form_names")
                 if r["local_language_id"] == ENGLISH and r["pokemon_name"]}

    types = defaultdict(list)
    for r in sorted(rows(folder, "pokemon_types"), key=lambda r: int(r["slot"])):
        types[r["pokemon_id"]].append(type_name[r["type_id"]])
    past = defaultdict(lambda: defaultdict(list))
    for r in sorted(rows(folder, "pokemon_types_past"), key=lambda r: int(r["slot"])):
        past[r["pokemon_id"]][int(r["generation_id"])].append(type_name[r["type_id"]])

    dex = {}
    for r in rows(folder, "pokemon"):
        slug = r["identifier"]
        if any(s in slug for s in SKIP) or r["id"] not in form_of:
            continue
        sp = species[r["species_id"]]
        form = form_of[r["id"]]
        is_default = r["is_default"] == "1"
        dex[slug] = {
            "name": species_name[r["species_id"]] if is_default
                    else form_name.get(form["id"], species_name[r["species_id"]]),
            "species": species_name[r["species_id"]],
            "dex": int(r["species_id"]),
            "gen": max(int(sp["generation_id"]), vg_gen[form["introduced_in_version_group_id"]]),
            "default": is_default,
            "types": types[r["id"]],
            # [gen, types]: the types used up to and including that generation.
            "past": [[g, t] for g, t in sorted(past[r["id"]].items())],
        }
    out.write_text(json.dumps(dex, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(dex)} entries to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
