"""Common crops of Polish farms, added to the shared crop catalog by
`manage.py seed_crops` (run on every start, see docker-entrypoint.sh).

Names are stored as data in Polish, like the crops users add themselves.
The description holds the crop group shown in the crop list.
"""

CROP_GROUPS = {
    "Zboża": (
        "Pszenica", "Żyto", "Jęczmień", "Owies", "Pszenżyto", "Orkisz",
        "Gryka", "Proso", "Kukurydza", "Kukurydza na kiszonkę", "Sorgo",
    ),
    "Rośliny oleiste": (
        "Rzepak", "Rzepik", "Słonecznik", "Len oleisty", "Soja", "Gorczyca", "Mak",
    ),
    "Rośliny strączkowe": (
        "Groch", "Bobik", "Łubin", "Fasola", "Wyka", "Soczewica",
    ),
    "Okopowe i przemysłowe": (
        "Ziemniaki", "Burak cukrowy", "Burak pastewny", "Konopie włókniste",
        "Tytoń", "Chmiel",
    ),
    "Rośliny pastewne": (
        "Lucerna", "Koniczyna", "Trawy na zielonkę", "Mieszanka zbożowo-strączkowa",
        "Łąka / pastwisko",
    ),
    "Warzywa": (
        "Marchew", "Cebula", "Czosnek", "Kapusta", "Kalafior", "Brokuł",
        "Pomidor", "Ogórek", "Papryka", "Pietruszka", "Seler", "Por",
        "Burak ćwikłowy", "Sałata", "Dynia", "Cukinia", "Szparagi",
    ),
    "Owoce": (
        "Truskawki", "Maliny", "Porzeczki", "Borówka amerykańska", "Aronia",
        "Jabłonie", "Grusze", "Śliwy", "Wiśnie", "Czereśnie",
    ),
}


def catalog():
    """(name, group) pairs of the whole catalog."""
    return [(name, group) for group, names in CROP_GROUPS.items() for name in names]
