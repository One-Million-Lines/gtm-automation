"""Role matcher — pure module, no DB, no I/O.

Maps a free-form job_title to one of a fixed set of normalized buckets, and
optionally elevates priority/confidence when the title hits an ICP target persona.
"""
from __future__ import annotations

import re

# (bucket, list of substring patterns — case-insensitive, matched after punctuation strip)
ROLE_RULES: list[tuple[str, list[str]]] = [
    ("founder",             ["founder", "co-founder", "cofounder", "ceo", "chief executive"]),
    ("marketing_lead",      ["cmo", "vp marketing", "vp of marketing", "marketing director",
                             "head of marketing", "director of marketing"]),
    ("growth_lead",         ["head of growth", "growth lead", "vp growth", "director of growth"]),
    ("crm_lead",            ["head of crm", "crm manager", "director of crm", "crm lead"]),
    ("lifecycle_marketing", ["lifecycle marketing", "lifecycle manager", "retention marketing"]),
    ("email_marketing",     ["email marketing", "email manager"]),
    ("ecommerce_lead",      ["ecommerce manager", "head of ecommerce", "e-commerce manager",
                             "director of ecommerce", "head of e-commerce"]),
    ("revops",              ["revops", "revenue operations"]),
    ("ops_lead",            ["operations manager", "head of operations", "coo", "chief operating"]),
    ("sales_lead",          ["vp sales", "head of sales", "sales director", "cro"]),
]

# Priority order when multiple buckets hit on the same title (lower wins).
_BUCKET_RANK: dict[str, int] = {b: i for i, (b, _) in enumerate(ROLE_RULES)}

_PUNCT_RE = re.compile(r"[^a-z0-9\s\-/]+")
_WS_RE = re.compile(r"\s+")


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    s = text.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _persona_hits(title_norm: str, personas: list[str] | None) -> tuple[int | None, str | None]:
    """Return (priority, matched_persona) — priority is 1-based persona index."""
    if not personas:
        return None, None
    for idx, p in enumerate(personas):
        pn = _normalize(p)
        if pn and pn in title_norm:
            return idx + 1, p
    return None, None


def match_role(job_title: str | None, target_personas: list[str] | None = None) -> dict:
    """Return {is_match, normalized_role, priority, confidence, reason}.

    Match path:
      1) exact persona substring match (case-insensitive) — confidence 0.95,
         priority = persona index + 1, normalized_role = best ROLE_RULES bucket
         hit on the title (or persona) if any.
      2) ROLE_RULES substring match — confidence 0.7, priority None.

    Multiple bucket hits → lowest _BUCKET_RANK wins (founder > marketing_lead > …).
    Empty/whitespace title → is_match=False.
    """
    title_norm = _normalize(job_title)
    if not title_norm:
        return {"is_match": False, "normalized_role": None, "priority": None,
                "confidence": 0.0, "reason": "empty job_title"}

    # Find all matching buckets via ROLE_RULES.
    bucket_hits: list[tuple[int, str, str]] = []  # (rank, bucket, matched_pattern)
    for bucket, patterns in ROLE_RULES:
        for p in patterns:
            if p in title_norm:
                bucket_hits.append((_BUCKET_RANK[bucket], bucket, p))
                break
    bucket_hits.sort(key=lambda t: t[0])
    best_bucket = bucket_hits[0][1] if bucket_hits else None
    best_pattern = bucket_hits[0][2] if bucket_hits else None

    # Persona match (case-insensitive substring).
    priority, matched_persona = _persona_hits(title_norm, target_personas)

    if matched_persona is not None:
        return {
            "is_match": True,
            "normalized_role": best_bucket,
            "priority": priority,
            "confidence": 0.95,
            "reason": f"matches target persona '{matched_persona}'",
        }

    if best_bucket is not None:
        # Match by rule, but no ICP persona — still a match (caller decides whether
        # to require persona). Priority is None.
        return {
            "is_match": True,
            "normalized_role": best_bucket,
            "priority": None,
            "confidence": 0.7,
            "reason": f"role rule '{best_pattern}' -> {best_bucket}",
        }

    return {"is_match": False, "normalized_role": None, "priority": None,
            "confidence": 0.0, "reason": "no role match"}
