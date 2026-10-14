"""Keyword-based auto-categorization for imported expenses.

Given a free-text description, guess the most likely category by matching
against keyword lists tuned for everyday spending in Geneva. This is a simple,
transparent rule engine — no ML, easy to extend: just add keywords below.
"""

from __future__ import annotations

# category -> keywords (all matched lowercase, as substrings of the description)
RULES: dict[str, list[str]] = {
    "Rent": ["rent", "loyer", "regie", "régie", "landlord", "bail"],
    "Groceries": [
        "migros", "coop", "denner", "aldi", "lidl", "manor food", "grocery",
        "supermarket", "épicerie", "epicerie", "carrefour", "naville",
    ],
    "Restaurants": [
        "restaurant", "resto", "cafe", "café", "bar", "brasserie", "bistro",
        "mcdonald", "burger", "pizza", "kebab", "starbucks", "lunch", "dinner",
        "uber eats", "eat", "takeaway", "coffee",
    ],
    "Transport": [
        "tpg", "cff", "sbb", "train", "bus", "tram", "uber", "taxi", "mobility",
        "shell", "esso", "bp ", "fuel", "essence", "parking", "sncf", "flixbus",
    ],
    "Health & Insurance": [
        "lamal", "assura", "css", "helsana", "groupe mutuel", "swica", "sanitas",
        "insurance", "assurance", "pharmacy", "pharmacie", "hopital", "hôpital",
        "doctor", "medecin", "médecin", "dentist", "dentiste", "health",
    ],
    "Utilities": [
        "sig", "electricity", "electricité", "électricité", "water", "gas",
        "internet", "swisscom", "salt", "sunrise", "mobile", "phone", "telecom",
        "netflix", "spotify", "subscription", "abonnement",
    ],
    "Shopping": [
        "manor", "h&m", "hm ", "zara", "uniqlo", "zalando", "amazon", "ikea",
        "fnac", "clothes", "vetements", "vêtements", "digitec", "galaxus",
        "decathlon", "shopping",
    ],
    "Leisure": [
        "cinema", "cinéma", "pathe", "pathé", "netflix", "concert", "museum",
        "musee", "musée", "gym", "fitness", "sport", "book", "livre", "game",
        "steam", "theatre", "théâtre", "club",
    ],
    "Travel": [
        "hotel", "airbnb", "booking", "flight", "easyjet", "swiss air", "vol",
        "voyage", "travel", "trip", "zermatt", "geneva airport", "ryanair",
    ],
}

DEFAULT_CATEGORY = "Other"


def guess_category(description: str) -> str:
    """Return the best-matching category for a description, or "Other"."""
    if not description:
        return DEFAULT_CATEGORY
    text = description.lower()

    best_category = DEFAULT_CATEGORY
    best_len = 0
    # Prefer the longest matching keyword so "manor food" -> Groceries wins
    # over a shorter, less specific match.
    for category, keywords in RULES.items():
        for kw in keywords:
            if kw in text and len(kw) > best_len:
                best_category = category
                best_len = len(kw)
    return best_category
