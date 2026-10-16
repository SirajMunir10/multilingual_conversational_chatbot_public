"""Resolves free-text UAE locations against data/config/communities.json."""
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import load_config


def _norm(text: Optional[str]) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("\xa0", " ").lower()
    text = re.sub(r"[()\[\],.;:/\\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _aliases() -> List[Tuple[str, Dict[str, Any]]]:
    cfg = load_config("communities")
    entries: List[Tuple[str, Dict[str, Any]]] = []
    for c in cfg["communities"]:
        for alias in [c["name"], *c["aliases"]]:
            entries.append((_norm(alias), {"kind": "community", "name": c["name"], "emirate": c["emirate"]}))
    for key, e in cfg["emirates"].items():
        for alias in [e["label"], *e["aliases"]]:
            entries.append((_norm(alias), {"kind": "emirate", "name": e["label"], "emirate": key}))
    for alias in cfg["nationwide_aliases"]:
        entries.append((_norm(alias), {"kind": "nationwide", "name": "UAE", "emirate": None}))
    # Longest alias first so "damac hills" wins over "hills" and "dubai hills estate" over "dubai".
    return sorted(entries, key=lambda e: len(e[0]), reverse=True)


def resolve(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns {'kind','name','emirate'} for the most specific known location in text, or
    {'kind':'unknown','name':text} when a location was given but is not recognised."""
    if not text or not text.strip():
        return None
    haystack = f" {_norm(text)} "
    for alias, info in _aliases():
        if alias and f" {alias} " in haystack:
            return dict(info)
    return {"kind": "unknown", "name": text.strip(), "emirate": None}


def emirate_label(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    return load_config("communities")["emirates"].get(key, {}).get("label")


def matches(location: Optional[Dict[str, Any]], community: str, city: str) -> bool:
    """True when a listing (community/city strings) falls inside the resolved location."""
    if not location or location["kind"] == "nationwide":
        return True
    listing_loc = resolve(f"{community} {city}") or {}
    if location["kind"] == "community":
        community_loc = resolve(community) or {}
        return community_loc.get("kind") == "community" and community_loc.get("name") == location["name"]
    if location["kind"] == "emirate":
        city_loc = resolve(city) or {}
        return city_loc.get("emirate") == location["emirate"] or listing_loc.get("emirate") == location["emirate"]
    return False


def canonical_community(raw: str) -> Tuple[str, Optional[str]]:
    """Canonical community name and emirate key for a raw district string."""
    loc = resolve(raw)
    if loc and loc["kind"] == "community":
        return loc["name"], loc["emirate"]
    return re.sub(r"\s+", " ", (raw or "").replace("\xa0", " ")).strip(), (loc or {}).get("emirate")


def known_communities(emirate: Optional[str] = None) -> List[str]:
    return [c["name"] for c in load_config("communities")["communities"] if not emirate or c["emirate"] == emirate]
