"""Pluggable QualityChecker (File 14).

Inspects an outreach_message + contact and returns rule-based pass/fail with
an aggregate quality_score in [0,1].

Rules (RuleBasedQualityChecker):
  - subject_length    (30..80 chars)
  - body_word_count   (60..160 words)
  - merge_tags        (no leftover {{name}} or [[var]])
  - pii               (no SSN / credit-card-like / phone-in-body)
  - suppression       (contact email / domain not on suppression_list)
  - spam_words        (no obvious spam triggers; 30-word built-in list)

Pluggable provider pattern (mirrors File 09/10/11/12/13):
    set_default_quality_checker(fake)   # for tests
    get_default_quality_checker()
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------
QUALITY_RULES = (
    "subject_length",
    "body_word_count",
    "merge_tags",
    "pii",
    "suppression",
    "spam_words",
)

SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_CRITICAL = "critical"

# Built-in 30-word spam trigger list (lowercased substring scan).
SPAM_TRIGGERS = (
    "free", "guarantee", "act now", "limited time", "click here",
    "cash", "winner", "cheap", "prize", "earn $",
    "make money", "risk-free", "100% free", "viagra", "crypto",
    "urgent", "exclusive", "congratulations", "apply now", "incredible deal",
    "deal", "trial", "amazing", "double your", "extra income",
    "best price", "lifetime", "miracle", "instant", "weight loss",
)
assert len(SPAM_TRIGGERS) == 30

SUBJECT_MIN, SUBJECT_MAX = 30, 80
BODY_WORD_MIN, BODY_WORD_MAX = 60, 160

# Per-rule weights (suppression hard-fails -> score=0, passed=False).
RULE_WEIGHTS: dict[str, float] = {
    "subject_length":  1.0,
    "body_word_count": 1.0,
    "merge_tags":      1.0,
    "pii":             2.0,
    "suppression":     2.0,
    "spam_words":      1.0,
}

# Critical rules (any failure marks overall passed=False regardless of score).
CRITICAL_RULES = ("pii", "suppression")


# ---------------------------------------------------------------------------
# Helpers (verbatim per File 14 spec)
# ---------------------------------------------------------------------------
_MERGE_TAG_RE = re.compile(r"\{\{[^}]+\}\}|\[\[[^\]]+\]\]")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]?){13,16}\b")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.\-]?)?\(?\d{2,4}\)?[\s.\-]\d{2,4}[\s.\-]\d{2,4}(?:[\s.\-]\d{2,4})?"
)


def _scan_merge_tags(text: str) -> list[str]:
    if not text:
        return []
    return _MERGE_TAG_RE.findall(text)


def _scan_pii(text: str) -> list[dict]:
    if not text:
        return []
    hits: list[dict] = []
    for m in _SSN_RE.findall(text):
        hits.append({"kind": "ssn", "match": m})
    for m in _CC_RE.findall(text):
        digits = re.sub(r"[^\d]", "", m)
        if 13 <= len(digits) <= 16:
            hits.append({"kind": "credit_card", "match": m})
    for m in _PHONE_RE.findall(text):
        digits = re.sub(r"[^\d]", "", m)
        if len(digits) >= 9:
            hits.append({"kind": "phone", "match": m})
    return hits


def _scan_spam_words(text: str, words: tuple[str, ...] = SPAM_TRIGGERS) -> list[str]:
    if not text:
        return []
    low = text.lower()
    return [w for w in words if w in low]


def _check_suppression(repos, contact: Optional[dict]) -> dict:
    """Return {hit:bool, reason:str|None, matches:list[dict]}."""
    if not contact:
        return {"hit": False, "reason": None, "matches": []}
    email = (contact.get("email") or "").strip().lower()
    matches: list[dict] = []
    sup = getattr(repos, "suppression", None)
    if sup is None:
        return {"hit": False, "reason": None, "matches": []}
    if email:
        if sup.is_suppressed("email", email):
            matches.append({"type": "email", "value": email})
        domain = email.split("@")[-1] if "@" in email else None
        if domain and sup.is_suppressed("domain", domain):
            matches.append({"type": "domain", "value": domain})
    if matches:
        first = matches[0]
        return {
            "hit": True,
            "reason": f"contact {first['type']} '{first['value']}' is suppressed",
            "matches": matches,
        }
    return {"hit": False, "reason": None, "matches": []}


def _aggregate_score(rule_results: list[dict]) -> float:
    if not rule_results:
        return 0.0
    # Suppression / PII hard-fail collapses score to 0.
    for r in rule_results:
        if r.get("rule") in CRITICAL_RULES and not r.get("passed"):
            return 0.0
    total_w = 0.0
    earned = 0.0
    for r in rule_results:
        w = float(r.get("weight") or RULE_WEIGHTS.get(r.get("rule"), 1.0))
        total_w += w
        if r.get("passed"):
            earned += w
    if total_w <= 0:
        return 0.0
    return round(earned / total_w, 4)


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------
@dataclass
class RuleResult:
    rule: str
    passed: bool
    reason: str
    severity: str = SEVERITY_INFO
    weight: float = 1.0

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "passed": bool(self.passed),
            "reason": self.reason,
            "severity": self.severity,
            "weight": float(self.weight),
        }


@dataclass
class QualityResult:
    checker: str
    score: float
    passed: bool
    rule_results: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Checker protocol + impls
# ---------------------------------------------------------------------------
class QualityChecker(Protocol):
    name: str

    def check(self, *, message: dict, contact: Optional[dict], repos: Any) -> QualityResult: ...


def _word_count(text: str) -> int:
    if not text:
        return 0
    return len([w for w in re.split(r"\s+", text.strip()) if w])


@dataclass
class RuleBasedQualityChecker:
    name: str = "rule_based"
    spam_words: tuple[str, ...] = SPAM_TRIGGERS
    min_score: float = 0.6

    def check(self, *, message: dict, contact: Optional[dict], repos: Any) -> QualityResult:
        subject = message.get("subject") or ""
        body = message.get("body") or ""
        rule_results: list[dict] = []

        # subject_length
        slen = len(subject)
        sub_ok = SUBJECT_MIN <= slen <= SUBJECT_MAX
        rule_results.append(RuleResult(
            rule="subject_length",
            passed=sub_ok,
            reason=(
                f"subject length {slen} ok ({SUBJECT_MIN}-{SUBJECT_MAX})"
                if sub_ok else
                f"subject length {slen} outside {SUBJECT_MIN}-{SUBJECT_MAX}"
            ),
            severity=SEVERITY_WARN if not sub_ok else SEVERITY_INFO,
            weight=RULE_WEIGHTS["subject_length"],
        ).to_dict())

        # body_word_count
        wc = _word_count(body)
        wc_ok = BODY_WORD_MIN <= wc <= BODY_WORD_MAX
        rule_results.append(RuleResult(
            rule="body_word_count",
            passed=wc_ok,
            reason=(
                f"body word count {wc} ok ({BODY_WORD_MIN}-{BODY_WORD_MAX})"
                if wc_ok else
                f"body word count {wc} outside {BODY_WORD_MIN}-{BODY_WORD_MAX}"
            ),
            severity=SEVERITY_WARN if not wc_ok else SEVERITY_INFO,
            weight=RULE_WEIGHTS["body_word_count"],
        ).to_dict())

        # merge_tags
        leftovers = _scan_merge_tags(subject) + _scan_merge_tags(body)
        mt_ok = len(leftovers) == 0
        rule_results.append(RuleResult(
            rule="merge_tags",
            passed=mt_ok,
            reason=(
                "no merge-tag leftovers"
                if mt_ok else
                f"unresolved merge tags: {leftovers[:5]}"
            ),
            severity=SEVERITY_WARN if not mt_ok else SEVERITY_INFO,
            weight=RULE_WEIGHTS["merge_tags"],
        ).to_dict())

        # pii (body only — addresses/phones in signatures should be flagged too)
        pii_hits = _scan_pii(body)
        pii_ok = len(pii_hits) == 0
        rule_results.append(RuleResult(
            rule="pii",
            passed=pii_ok,
            reason=(
                "no PII patterns detected"
                if pii_ok else
                f"PII detected: {[h['kind'] for h in pii_hits][:3]}"
            ),
            severity=SEVERITY_CRITICAL if not pii_ok else SEVERITY_INFO,
            weight=RULE_WEIGHTS["pii"],
        ).to_dict())

        # suppression
        sup = _check_suppression(repos, contact)
        sup_ok = not sup["hit"]
        rule_results.append(RuleResult(
            rule="suppression",
            passed=sup_ok,
            reason=(
                "contact not on suppression list"
                if sup_ok else
                sup["reason"] or "suppression hit"
            ),
            severity=SEVERITY_CRITICAL if not sup_ok else SEVERITY_INFO,
            weight=RULE_WEIGHTS["suppression"],
        ).to_dict())

        # spam_words
        spam_hits = _scan_spam_words(f"{subject}\n{body}", self.spam_words)
        spam_ok = len(spam_hits) == 0
        rule_results.append(RuleResult(
            rule="spam_words",
            passed=spam_ok,
            reason=(
                "no spam triggers"
                if spam_ok else
                f"spam triggers: {spam_hits[:5]}"
            ),
            severity=SEVERITY_WARN if not spam_ok else SEVERITY_INFO,
            weight=RULE_WEIGHTS["spam_words"],
        ).to_dict())

        score = _aggregate_score(rule_results)
        critical_failed = any(
            (r["rule"] in CRITICAL_RULES and not r["passed"]) for r in rule_results
        )
        passed = (not critical_failed) and (score >= self.min_score)
        return QualityResult(
            checker=self.name,
            score=score,
            passed=passed,
            rule_results=rule_results,
        )


@dataclass
class FakeQualityChecker:
    """Deterministic checker for tests."""
    name: str = "fake"
    fixed_score: float = 0.9
    fixed_passed: bool = True
    extra_rules: list[dict] = field(default_factory=list)

    def check(self, *, message: dict, contact: Optional[dict], repos: Any) -> QualityResult:
        rules = [{
            "rule": "fake_ok",
            "passed": True,
            "reason": "fake checker always passes",
            "severity": SEVERITY_INFO,
            "weight": 1.0,
        }]
        rules.extend(self.extra_rules or [])
        return QualityResult(
            checker=self.name,
            score=float(self.fixed_score),
            passed=bool(self.fixed_passed),
            rule_results=rules,
        )


@dataclass
class LLMQualityChecker:
    """LLM-augmented checker. Runs RuleBasedQualityChecker first, then optionally
    calls `llm.call_openai_tools(...)` to add a `llm_review` rule. Degrades to
    pure rule-based when llm is None.
    """
    llm: Any = None
    model: str = "gpt-4o-mini"
    name: str = "llm_augmented"
    base: Optional[RuleBasedQualityChecker] = None

    def check(self, *, message: dict, contact: Optional[dict], repos: Any) -> QualityResult:
        base = self.base or RuleBasedQualityChecker()
        base_result = base.check(message=message, contact=contact, repos=repos)
        if self.llm is None:
            return QualityResult(
                checker=self.name,
                score=base_result.score,
                passed=base_result.passed,
                rule_results=base_result.rule_results,
            )
        try:
            prompt = (
                "You are an outbound email QA reviewer. Reply JSON "
                '{"passed": bool, "reason": str}. '
                f"Subject: {message.get('subject')!r}\nBody:\n{message.get('body')}"
            )
            resp, _usage = self.llm.call_openai_tools(
                messages=[{"role": "user", "content": prompt}],
                model=self.model, response_format="json",
            )
            llm_passed = bool((resp or {}).get("passed", True))
            llm_reason = str((resp or {}).get("reason") or "llm review")
        except Exception as exc:  # pragma: no cover - defensive
            llm_passed = True
            llm_reason = f"llm review skipped: {exc}"

        rules = list(base_result.rule_results) + [{
            "rule": "llm_review",
            "passed": llm_passed,
            "reason": llm_reason,
            "severity": SEVERITY_WARN if not llm_passed else SEVERITY_INFO,
            "weight": 1.0,
        }]
        score = _aggregate_score(rules)
        critical_failed = any(
            (r["rule"] in CRITICAL_RULES and not r["passed"]) for r in rules
        )
        passed = (not critical_failed) and llm_passed and (score >= base.min_score)
        return QualityResult(
            checker=self.name, score=score, passed=passed, rule_results=rules,
        )


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------
_default_checker: QualityChecker = RuleBasedQualityChecker()


def get_default_quality_checker() -> QualityChecker:
    return _default_checker


def set_default_quality_checker(checker: Optional[QualityChecker]) -> None:
    global _default_checker
    _default_checker = checker if checker is not None else RuleBasedQualityChecker()


def check_quality(
    *, message: dict, contact: Optional[dict], repos: Any,
    checker: Optional[QualityChecker] = None,
) -> QualityResult:
    return (checker or _default_checker).check(message=message, contact=contact, repos=repos)
