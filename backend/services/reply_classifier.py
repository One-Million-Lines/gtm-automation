"""Pluggable ReplyClassifier (File 16).

Implementations:
  - LLMReplyClassifier:        calls llm.call_openai_tools with strict JSON schema
  - RuleBasedReplyClassifier:  regex-based fallback
  - FakeReplyClassifier:       deterministic for tests

Pluggable provider pattern (mirrors File 15 email_sender):
    set_default_reply_classifier(fake)
    get_default_reply_classifier()
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------
REPLY_INTENTS = ("positive", "negative", "oof", "unsubscribe", "info_request", "neutral")


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
class ReplyClassifier(Protocol):
    name: str

    def classify(
        self, *,
        body: str,
        subject: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> dict:
        """Return {intent, confidence, reason, classifier}."""
        ...


# ---------------------------------------------------------------------------
# Rule-based classifier (regex fallback)
# ---------------------------------------------------------------------------
_RX_UNSUBSCRIBE = re.compile(
    r"\b(unsubscribe|stop emailing|remove me|opt[- ]out|take me off|do not (email|contact))\b",
    re.IGNORECASE,
)
_RX_OOO = re.compile(
    r"\b(out of (office|the office)|on (vacation|holiday|leave|pto|annual leave)|"
    r"away from (my|the) (desk|office)|auto[- ]?reply|automatic reply)\b",
    re.IGNORECASE,
)
_RX_NEGATIVE = re.compile(
    r"\b(not interested|no thanks|no thank you|please stop|don'?t contact|"
    r"already have|wrong person|not (a|the) (right|good) (fit|time))\b",
    re.IGNORECASE,
)
_RX_POSITIVE = re.compile(
    r"\b(interested|sounds good|let'?s (chat|talk|connect|schedule)|happy to|"
    r"send (over|me)|book a (call|meeting|time)|tell me more|yes,? please)\b",
    re.IGNORECASE,
)


@dataclass
class RuleBasedReplyClassifier:
    name: str = "rule_based"

    def classify(
        self, *,
        body: str,
        subject: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> dict:
        text = f"{subject or ''}\n{body or ''}"
        if _RX_UNSUBSCRIBE.search(text):
            return {"intent": "unsubscribe", "confidence": 0.95,
                    "reason": "matched unsubscribe phrase", "classifier": self.name}
        if _RX_OOO.search(text):
            return {"intent": "oof", "confidence": 0.9,
                    "reason": "matched OOO phrase", "classifier": self.name}
        if _RX_NEGATIVE.search(text):
            return {"intent": "negative", "confidence": 0.8,
                    "reason": "matched negative phrase", "classifier": self.name}
        if "?" in (body or ""):
            return {"intent": "info_request", "confidence": 0.6,
                    "reason": "contains question mark", "classifier": self.name}
        if _RX_POSITIVE.search(text):
            return {"intent": "positive", "confidence": 0.75,
                    "reason": "matched positive phrase", "classifier": self.name}
        return {"intent": "neutral", "confidence": 0.5,
                "reason": "no rules matched", "classifier": self.name}


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------
@dataclass
class LLMReplyClassifier:
    """Real LLM-backed classifier. Degrades to RuleBasedReplyClassifier when llm is None."""
    llm: Any = None
    model: str = "gpt-4o-mini"
    name: str = "llm"
    fallback: ReplyClassifier = field(default_factory=RuleBasedReplyClassifier)

    def classify(
        self, *,
        body: str,
        subject: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> dict:
        if self.llm is None:
            res = self.fallback.classify(
                body=body, subject=subject, from_email=from_email,
            )
            res["classifier"] = f"{self.name}_fallback({res['classifier']})"
            return res
        prompt = (
            "Classify this inbound email reply into ONE of these intents: "
            f"{', '.join(REPLY_INTENTS)}. "
            'Reply strict JSON {"intent": str, "confidence": float, "reason": str}. '
            f"Subject: {subject!r}\nFrom: {from_email!r}\nBody:\n{body or ''}"
        )
        try:
            payload, _usage = self.llm.call_openai_tools(
                messages=[{"role": "user", "content": prompt}],
                llm_model=self.model,
                response_format="json",
            )
            intent = str((payload or {}).get("intent") or "neutral").lower()
            if intent not in REPLY_INTENTS:
                intent = "neutral"
            try:
                conf = float((payload or {}).get("confidence") or 0.5)
            except Exception:
                conf = 0.5
            reason = str((payload or {}).get("reason") or "")
            return {
                "intent": intent,
                "confidence": max(0.0, min(1.0, conf)),
                "reason": reason,
                "classifier": self.name,
            }
        except Exception as exc:  # pragma: no cover - defensive
            res = self.fallback.classify(
                body=body, subject=subject, from_email=from_email,
            )
            res["classifier"] = f"{self.name}_error({res['classifier']})"
            res["reason"] = f"llm_error: {exc}"
            return res


# ---------------------------------------------------------------------------
# Fake classifier (deterministic for tests)
# ---------------------------------------------------------------------------
@dataclass
class FakeReplyClassifier:
    name: str = "fake"
    intent: str = "positive"
    confidence: float = 0.99

    def classify(
        self, *,
        body: str,
        subject: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "reason": "fake",
            "classifier": self.name,
        }


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------
_default_classifier: ReplyClassifier = RuleBasedReplyClassifier()


def get_default_reply_classifier() -> ReplyClassifier:
    return _default_classifier


def set_default_reply_classifier(c: Optional[ReplyClassifier]) -> None:
    global _default_classifier
    _default_classifier = c if c is not None else RuleBasedReplyClassifier()


def classify_reply(
    *,
    body: str,
    subject: Optional[str] = None,
    from_email: Optional[str] = None,
    classifier: Optional[ReplyClassifier] = None,
) -> dict:
    return (classifier or _default_classifier).classify(
        body=body, subject=subject, from_email=from_email,
    )
