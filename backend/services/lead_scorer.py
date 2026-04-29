"""Pluggable LeadScorer (File 12).

Computes per-lead:
  - fit_score   (ICP alignment: industry / role / seniority / geo / employee size)
  - intent_score (signal-strength weighted sum w/ recency decay)
  - combined_score = 0.6*fit + 0.4*intent
  - priority_tier  A/B/C/D
  - scoring_explanation (per-criterion contributions + matched/missed
                          + signal contributions w/ weights)

Pluggable provider pattern (mirrors File 09/10/11):
    set_default_lead_scorer(fake)   # for tests
    get_default_lead_scorer()
    score_lead(repos, lead, ...)    # convenience
"""
from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


# --- Taxonomy & weights -----------------------------------------------------

# Per-criterion weights inside fit_score (must sum to 1.0)
FIT_WEIGHTS: dict[str, float] = {
    "industry":   0.30,
    "role":       0.25,
    "seniority":  0.20,
    "geo":        0.10,
    "size":       0.15,
}

# Per-signal-type weights inside intent_score
SIGNAL_WEIGHTS: dict[str, float] = {
    "hiring_intent":      1.0,
    "funding":            1.0,
    "tech_stack_change":  0.8,
    "hiring_pace":        0.7,
    "news_mention":       0.6,
    "social_activity":    0.4,
    "role_change":        0.9,
    "linkedin_activity":  0.3,
}

# combined = FIT_RATIO*fit + INTENT_RATIO*intent
FIT_RATIO = 0.6
INTENT_RATIO = 0.4

# Recency half-life in days for intent decay
INTENT_HALFLIFE_DAYS = 30.0

# Tier thresholds applied on combined_score (0..1)
TIER_THRESHOLDS: list[tuple[str, float]] = [
    ("A", 0.75),
    ("B", 0.55),
    ("C", 0.35),
    ("D", 0.0),
]

PRIORITY_TIERS = ("A", "B", "C", "D")


# --- Helpers ----------------------------------------------------------------

def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _norm_list(xs: Any) -> list[str]:
    if not xs:
        return []
    if isinstance(xs, str):
        return [_norm(xs)] if xs.strip() else []
    return [_norm(x) for x in xs if str(x).strip()]


def _any_match(target: str, candidates: list[str]) -> bool:
    if not target or not candidates:
        return False
    t = _norm(target)
    for c in candidates:
        if not c:
            continue
        if t == c or c in t or t in c:
            return True
    return False


def _parse_dt(v: Any) -> Optional[_dt.datetime]:
    if not v:
        return None
    if isinstance(v, _dt.datetime):
        return v
    s = str(v).replace("Z", "+00:00")
    try:
        return _dt.datetime.fromisoformat(s)
    except Exception:
        # SQLite default 'YYYY-MM-DD HH:MM:SS'
        try:
            return _dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def _recency_factor(created_at: Any, *, now: Optional[_dt.datetime] = None,
                    halflife_days: float = INTENT_HALFLIFE_DAYS) -> float:
    """Half-life decay factor in (0..1]. Newer = closer to 1."""
    dt = _parse_dt(created_at)
    if dt is None:
        return 1.0
    now = now or _dt.datetime.now(dt.tzinfo) if dt.tzinfo else _dt.datetime.utcnow()
    age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
    return float(0.5 ** (age_days / halflife_days))


# --- ICP-criterion matchers -------------------------------------------------

def match_industry(icp: dict, company: dict) -> tuple[float, dict]:
    targets = _norm_list(icp.get("target_industries"))
    if not targets:
        return 1.0, {"matched": True, "reason": "icp_has_no_industry_target"}
    co = _norm(company.get("industry"))
    if not co:
        return 0.0, {"matched": False, "reason": "company_industry_missing"}
    ok = _any_match(co, targets)
    return (1.0 if ok else 0.0), {"matched": ok, "company_industry": co, "targets": targets}


def match_role(icp: dict, contact: Optional[dict]) -> tuple[float, dict]:
    targets = _norm_list(icp.get("target_roles"))
    if not targets:
        return 1.0, {"matched": True, "reason": "icp_has_no_role_target"}
    if not contact:
        return 0.0, {"matched": False, "reason": "no_contact"}
    role = _norm(contact.get("normalized_role") or contact.get("job_title"))
    if not role:
        return 0.0, {"matched": False, "reason": "contact_role_missing"}
    ok = _any_match(role, targets)
    return (1.0 if ok else 0.0), {"matched": ok, "contact_role": role, "targets": targets}


SENIORITY_ORDER = ("intern", "junior", "mid", "senior", "lead", "manager",
                   "director", "vp", "c_level", "founder")


def _seniority_from_title(title: str) -> str:
    t = _norm(title)
    if not t:
        return ""
    if any(k in t for k in ("ceo", "cto", "cfo", "coo", "cmo", "chief")):
        return "c_level"
    if "founder" in t or "co-founder" in t:
        return "founder"
    if t.startswith("vp") or "vice president" in t or " vp " in f" {t} ":
        return "vp"
    if "director" in t:
        return "director"
    if "head of" in t or "head, " in t:
        return "director"
    if "manager" in t:
        return "manager"
    if "lead" in t:
        return "lead"
    if "senior" in t or "sr." in t or "sr " in t:
        return "senior"
    if "junior" in t or "jr." in t:
        return "junior"
    if "intern" in t:
        return "intern"
    return "mid"


def match_seniority(icp: dict, contact: Optional[dict]) -> tuple[float, dict]:
    targets = _norm_list(icp.get("target_seniorities"))
    if not targets:
        return 1.0, {"matched": True, "reason": "icp_has_no_seniority_target"}
    if not contact:
        return 0.0, {"matched": False, "reason": "no_contact"}
    sen = _seniority_from_title(contact.get("job_title") or "")
    ok = sen in targets
    return (1.0 if ok else 0.0), {"matched": ok, "contact_seniority": sen, "targets": targets}


def match_geo(icp: dict, company: dict, contact: Optional[dict]) -> tuple[float, dict]:
    targets = _norm_list(icp.get("target_geographies"))
    if not targets:
        return 1.0, {"matched": True, "reason": "icp_has_no_geo_target"}
    candidates: list[str] = []
    for src in (company, contact or {}):
        for k in ("country", "city"):
            v = _norm(src.get(k))
            if v:
                candidates.append(v)
    if not candidates:
        return 0.0, {"matched": False, "reason": "no_geo_data"}
    ok = any(_any_match(c, targets) for c in candidates)
    return (1.0 if ok else 0.0), {"matched": ok, "candidates": candidates, "targets": targets}


def match_size(icp: dict, company: dict) -> tuple[float, dict]:
    lo = icp.get("target_company_size_min")
    hi = icp.get("target_company_size_max")
    if lo is None and hi is None:
        return 1.0, {"matched": True, "reason": "icp_has_no_size_target"}
    n = company.get("employee_count")
    if n is None:
        return 0.0, {"matched": False, "reason": "company_size_missing"}
    try:
        n = int(n)
    except Exception:
        return 0.0, {"matched": False, "reason": "company_size_invalid"}
    if lo is not None and n < int(lo):
        return 0.0, {"matched": False, "n": n, "min": int(lo), "max": hi}
    if hi is not None and n > int(hi):
        return 0.0, {"matched": False, "n": n, "min": lo, "max": int(hi)}
    return 1.0, {"matched": True, "n": n, "min": lo, "max": hi}


# --- Aggregators ------------------------------------------------------------

def aggregate_signals(signals: list[dict], *, now: Optional[_dt.datetime] = None,
                      weights: dict[str, float] = SIGNAL_WEIGHTS) -> tuple[float, list[dict]]:
    """Return (intent_score in 0..1, contributions list)."""
    contribs: list[dict] = []
    if not signals:
        return 0.0, contribs
    weighted_sum = 0.0
    weight_sum = 0.0
    for s in signals:
        st = str(s.get("signal_type") or "")
        w = float(weights.get(st, 0.5))
        strength = float(s.get("strength_score") or 0.0)
        recency = _recency_factor(s.get("created_at"), now=now)
        contribution = w * strength * recency
        weighted_sum += contribution
        weight_sum += w
        contribs.append({
            "signal_id": s.get("id"),
            "signal_type": st,
            "weight": w,
            "strength": strength,
            "recency": round(recency, 4),
            "contribution": round(contribution, 4),
        })
    if weight_sum <= 0:
        return 0.0, contribs
    raw = weighted_sum / weight_sum
    # squash to 0..1 (defensive)
    return max(0.0, min(1.0, raw)), contribs


def compute_fit(icp: dict, company: dict, contact: Optional[dict]) -> tuple[float, dict]:
    parts: dict[str, dict] = {}
    score = 0.0
    industry, info = match_industry(icp, company); parts["industry"] = {**info, "weight": FIT_WEIGHTS["industry"], "score": industry}
    role, info     = match_role(icp, contact);     parts["role"]     = {**info, "weight": FIT_WEIGHTS["role"],     "score": role}
    sen, info      = match_seniority(icp, contact); parts["seniority"] = {**info, "weight": FIT_WEIGHTS["seniority"], "score": sen}
    geo, info      = match_geo(icp, company, contact); parts["geo"]   = {**info, "weight": FIT_WEIGHTS["geo"],     "score": geo}
    size, info     = match_size(icp, company);     parts["size"]     = {**info, "weight": FIT_WEIGHTS["size"],     "score": size}

    score = (
        industry * FIT_WEIGHTS["industry"]
        + role     * FIT_WEIGHTS["role"]
        + sen      * FIT_WEIGHTS["seniority"]
        + geo      * FIT_WEIGHTS["geo"]
        + size     * FIT_WEIGHTS["size"]
    )
    return max(0.0, min(1.0, score)), parts


def tier_for(combined_score: float) -> str:
    for tier, threshold in TIER_THRESHOLDS:
        if combined_score >= threshold:
            return tier
    return "D"


# --- Result dataclass -------------------------------------------------------

@dataclass
class ScoreResult:
    fit_score: float
    intent_score: float
    combined_score: float
    priority_tier: str
    explanation: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "icp_fit_score": round(self.fit_score, 4),
            "signal_score": round(self.intent_score, 4),
            "final_score": round(self.combined_score, 4),
            "priority_tier": self.priority_tier,
            "scored_at": _dt.datetime.utcnow().isoformat(timespec="seconds"),
            "scoring_explanation": self.explanation,
        }


# --- Provider Protocol + Implementations ------------------------------------

class LeadScorer(Protocol):
    def score(
        self,
        *,
        icp: dict,
        company: dict,
        contact: Optional[dict],
        signals: list[dict],
    ) -> ScoreResult: ...


@dataclass
class RuleBasedLeadScorer:
    """Deterministic rule-based scorer (no network)."""
    fit_weights: dict[str, float] = field(default_factory=lambda: dict(FIT_WEIGHTS))
    signal_weights: dict[str, float] = field(default_factory=lambda: dict(SIGNAL_WEIGHTS))
    fit_ratio: float = FIT_RATIO
    intent_ratio: float = INTENT_RATIO

    def score(self, *, icp: dict, company: dict,
              contact: Optional[dict], signals: list[dict]) -> ScoreResult:
        fit, fit_parts = compute_fit(icp, company, contact)
        intent, sig_contribs = aggregate_signals(signals, weights=self.signal_weights)
        combined = self.fit_ratio * fit + self.intent_ratio * intent
        combined = max(0.0, min(1.0, combined))
        tier = tier_for(combined)
        explanation = {
            "scorer": "rule_based",
            "fit_ratio": self.fit_ratio,
            "intent_ratio": self.intent_ratio,
            "fit": {
                "score": round(fit, 4),
                "criteria": fit_parts,
                "matched": [k for k, v in fit_parts.items() if v.get("matched")],
                "missed":  [k for k, v in fit_parts.items() if not v.get("matched")],
            },
            "intent": {
                "score": round(intent, 4),
                "signal_count": len(signals),
                "contributions": sig_contribs,
                "halflife_days": INTENT_HALFLIFE_DAYS,
            },
            "combined": round(combined, 4),
            "tier": tier,
        }
        return ScoreResult(fit, intent, combined, tier, explanation)


@dataclass
class LLMAugmentedLeadScorer:
    """Rule-based + optional LLM nudge to combined score (-0.1..+0.1).

    The LLM call is opt-in via an injected callable (so tests/live can swap).
    Defaults to no-op (acts identical to RuleBasedLeadScorer).
    """
    base: RuleBasedLeadScorer = field(default_factory=RuleBasedLeadScorer)
    llm_call: Optional[Any] = None  # callable(prompt:str) -> dict {nudge: float, reason: str}

    def score(self, *, icp: dict, company: dict,
              contact: Optional[dict], signals: list[dict]) -> ScoreResult:
        base_res = self.base.score(icp=icp, company=company, contact=contact, signals=signals)
        nudge = 0.0
        nudge_reason = "llm_disabled"
        if callable(self.llm_call):
            try:
                prompt = (
                    f"Lead: company={company.get('name')!r} industry={company.get('industry')!r}; "
                    f"contact={(contact or {}).get('full_name')!r} title={(contact or {}).get('job_title')!r}; "
                    f"icp={icp.get('name')!r} fit={base_res.fit_score:.2f} intent={base_res.intent_score:.2f}"
                )
                out = self.llm_call(prompt) or {}
                nudge = max(-0.1, min(0.1, float(out.get("nudge") or 0.0)))
                nudge_reason = str(out.get("reason") or "llm_nudge")
            except Exception as e:
                nudge_reason = f"llm_error:{e}"
        combined = max(0.0, min(1.0, base_res.combined_score + nudge))
        tier = tier_for(combined)
        explanation = dict(base_res.explanation)
        explanation["scorer"] = "llm_augmented"
        explanation["llm"] = {"nudge": round(nudge, 4), "reason": nudge_reason}
        explanation["combined"] = round(combined, 4)
        explanation["tier"] = tier
        return ScoreResult(base_res.fit_score, base_res.intent_score, combined, tier, explanation)


@dataclass
class FakeLeadScorer:
    """Deterministic scorer for tests. Honors fit/intent overrides per (icp_id, lead key)."""
    fixed_fit: Optional[float] = None
    fixed_intent: Optional[float] = None
    fixed_tier: Optional[str] = None
    use_rules_fallback: bool = True
    _rule: RuleBasedLeadScorer = field(default_factory=RuleBasedLeadScorer)

    def score(self, *, icp: dict, company: dict,
              contact: Optional[dict], signals: list[dict]) -> ScoreResult:
        if self.use_rules_fallback and self.fixed_fit is None and self.fixed_intent is None:
            return self._rule.score(icp=icp, company=company, contact=contact, signals=signals)
        fit = self.fixed_fit if self.fixed_fit is not None else 0.5
        intent = self.fixed_intent if self.fixed_intent is not None else 0.5
        combined = max(0.0, min(1.0, FIT_RATIO * fit + INTENT_RATIO * intent))
        tier = self.fixed_tier or tier_for(combined)
        explanation = {
            "scorer": "fake",
            "fit": {"score": fit},
            "intent": {"score": intent, "signal_count": len(signals)},
            "combined": round(combined, 4),
            "tier": tier,
            "note": "FakeLeadScorer fixed output",
        }
        return ScoreResult(fit, intent, combined, tier, explanation)


# --- Module-level pluggable provider ---------------------------------------

_default_scorer: LeadScorer = RuleBasedLeadScorer()


def get_default_lead_scorer() -> LeadScorer:
    return _default_scorer


def set_default_lead_scorer(scorer: Optional[LeadScorer]) -> None:
    global _default_scorer
    _default_scorer = scorer if scorer is not None else RuleBasedLeadScorer()


def score_lead(*, icp: dict, company: dict, contact: Optional[dict],
               signals: list[dict], scorer: Optional[LeadScorer] = None) -> ScoreResult:
    return (scorer or _default_scorer).score(
        icp=icp, company=company, contact=contact, signals=signals,
    )
