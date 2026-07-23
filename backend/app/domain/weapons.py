from __future__ import annotations

from collections.abc import Iterable

# CS2 weapon catalogue
WEAPON_CATALOG: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # pistols
    ("glock", "pistols", ("glock",)),
    ("usp_s", "pistols", ("usp",)),
    ("p2000", "pistols", ("hkp2000", "p2000")),
    ("p250", "pistols", ("p250",)),
    ("five_seven", "pistols", ("five-seven", "fiveseven")),
    ("tec9", "pistols", ("tec-9", "tec9")),
    ("cz75", "pistols", ("cz75",)),
    ("deagle", "pistols", ("deagle", "desert eagle")),
    ("dualies", "pistols", ("dual berettas", "dualberettas", "elite")),
    ("revolver", "pistols", ("revolver",)),
    # smgs
    ("mac10", "smgs", ("mac-10", "mac10")),
    ("mp9", "smgs", ("mp9",)),
    ("mp7", "smgs", ("mp7",)),
    ("mp5", "smgs", ("mp5",)),
    ("ump45", "smgs", ("ump",)),
    ("p90", "smgs", ("p90",)),
    ("bizon", "smgs", ("bizon",)),
    # rifles
    ("galil", "rifles", ("galil",)),
    ("famas", "rifles", ("famas",)),
    ("ak47", "rifles", ("ak-47", "ak47")),
    ("m4a4", "rifles", ("m4a4",)),
    ("m4a1_s", "rifles", ("m4a1-s", "m4a1_s", "m4a1")),
    ("sg553", "rifles", ("sg553", "sg 553", "sg556")),
    ("aug", "rifles", ("aug",)),
    # snipers
    ("ssg08", "snipers", ("ssg08", "ssg 08", "scout")),
    ("awp", "snipers", ("awp",)),
    ("g3sg1", "snipers", ("g3sg1",)),
    ("scar20", "snipers", ("scar-20", "scar20")),
    # heavy
    ("nova", "heavy", ("nova",)),
    ("xm1014", "heavy", ("xm1014",)),
    ("mag7", "heavy", ("mag-7", "mag7")),
    ("sawedoff", "heavy", ("sawed-off", "sawedoff", "sawed off")),
    ("m249", "heavy", ("m249",)),
    ("negev", "heavy", ("negev",)),
)

WEAPON_IDS: tuple[str, ...] = tuple(w[0] for w in WEAPON_CATALOG)


def weapons_present(inventory: Iterable[str]) -> list[str]:
    """Catalogue ids whose needle appears in any of the inventory strings."""
    hay = " ".join(str(x).lower() for x in inventory if x)
    return [wid for wid, _cat, needles in WEAPON_CATALOG if any(n in hay for n in needles)]
