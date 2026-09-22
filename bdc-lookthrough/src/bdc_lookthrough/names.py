"""Normalize BDC portfolio-company names so overlap is not string equality."""

from __future__ import annotations

import re

LEGAL_SUFFIXES = (
    r"\bincorporated\b",
    r"\bcorporation\b",
    r"\bcompany\b",
    r"\blimited\b",
    r"\bl\.?l\.?c\.?\b",
    r"\bl\.?l\.?p\.?\b",
    r"\bl\.?p\.?\b",
    r"\bllc\b",
    r"\bllp\b",
    r"\binc\b",
    r"\bcorp\b",
    r"\bltd\b",
    r"\bplc\b",
    r"\bco\b",
)

# Investment-type leftovers that edgartools sometimes emits as a "company".
JUNK_EXACT = {
    "subordinated",
    "senior",
    "equity",
    "preferred",
    "unsecured",
    "revolving",
    "revolver",
    "unitranche",
    "cash",
    "total",
    "investments",
    "other",
    "various",
    "first lien",
    "second lien",
    "delayed draw",
    "one stop",
    "unclassified",
    "loan",
    "note",
    "debt",
    "class a units",
    "common units",
}

# Bare queries that are industry/legal filler. Exact full-name match is still allowed.
GENERIC_TOKENS = frozenset(
    {
        "group",
        "groups",
        "parent",
        "holding",
        "holdings",
        "holdco",
        "capital",
        "acquisition",
        "international",
        "management",
        "software",
        "health",
        "services",
        "service",
        "partners",
        "partner",
        "funding",
        "borrower",
        "midco",
        "topco",
        "usa",
        "class",
        "common",
        "units",
        "unit",
        "and",
        "the",
        "company",
        "companies",
        "solutions",
        "global",
        "america",
        "american",
        "intermediate",
        "financial",
        "finance",
        "credit",
        "lending",
        "systems",
        "system",
        "tech",
        "technology",
        "technologies",
        "industries",
        "industry",
        "partners",
    }
)

AKA_SPLIT = re.compile(
    r"[\(\[]\s*(?P<label>d/?b/?a|dba|f/?k/?a|fka|formerly known as)\s*[:\-]?\s*(?P<name>[^\)\]]+)[\)\]]",
    re.I,
)

TRAILING_AKA = re.compile(
    r"\s+(?P<label>d/?b/?a|dba|f/?k/?a|fka|formerly known as)\s+[:\-]?\s*(?P<name>.+)$",
    re.I,
)


def _strip_legal(text: str) -> str:
    value = text
    for _ in range(4):
        nxt = value
        for pat in LEGAL_SUFFIXES:
            nxt = re.sub(pat, " ", nxt)
        nxt = re.sub(r"\s+", " ", nxt).strip()
        if nxt == value:
            break
        value = nxt
    return value


def normalize_borrower(name: str | None) -> str:
    """Lowercase legal name without Inc/LLC noise or footnote markers."""
    raw = (name or "").replace("\u00a0", " ").strip()
    if raw == "":
        return ""
    raw = re.sub(r"\[[^\]]*\]", " ", raw)
    raw = re.sub(r"\([0-9ivx]+\)", " ", raw, flags=re.I)
    raw = re.sub(r"footnote\s*\d+", " ", raw, flags=re.I)
    raw = raw.lower().replace("&", " and ")
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = _strip_legal(raw)
    raw = re.sub(r"\b\d{1,2}$", "", raw).strip()
    return re.sub(r"\s+", " ", raw).strip()


def aliases_for(name: str | None) -> list[str]:
    """Primary normalized name plus d/b/a and f/k/a aliases, de-duplicated."""
    raw = (name or "").replace("\u00a0", " ").strip()
    if raw == "":
        return []
    aliases: list[str] = []
    remainder = raw
    for match in AKA_SPLIT.finditer(raw):
        extra = normalize_borrower(match.group("name"))
        if extra:
            aliases.append(extra)
        remainder = remainder.replace(match.group(0), " ")
    trailing = TRAILING_AKA.search(remainder)
    if trailing:
        extra = normalize_borrower(trailing.group("name"))
        if extra:
            aliases.append(extra)
        remainder = remainder[: trailing.start()]
    primary = normalize_borrower(remainder)
    ordered: list[str] = []
    for item in [primary, *aliases]:
        if item and item not in ordered and not is_junk_borrower(item):
            ordered.append(item)
    return ordered


def is_junk_borrower(norm: str | None) -> bool:
    value = (norm or "").strip()
    if len(value) < 3:
        return True
    if value in JUNK_EXACT:
        return True
    if re.fullmatch(r"z\d+", value):
        return True
    return False


def query_matches(query_norm: str, names: list[str]) -> bool:
    """True if a user query hits a primary name or alias.

    Generic tokens such as ``group`` or ``software`` only match a full name.
    """
    q = (query_norm or "").strip()
    if len(q) < 3:
        return False
    generic = q in GENERIC_TOKENS
    for name in names:
        if not name:
            continue
        if q == name:
            return True
        if generic:
            continue
        if len(q) >= 4 and name.startswith(q):
            return True
        if len(q) >= 6 and len(name) >= 6 and q.startswith(name):
            return True
        tokens = name.split()
        if len(q) >= 5 and q in tokens:
            return True
        if len(q) >= 6 and q in name:
            return True
    return False
