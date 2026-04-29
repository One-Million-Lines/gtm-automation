"""Pluggable OutreachGenerator (File 13).

Generates personalized cold-email drafts (subject + body + optional html)
grounded in:
  - ICP value_proposition / outreach_angle / pain_points
  - Lead fit-criteria matched list (from File 12 explanation)
  - Top-N (<=3) signal contributions (from File 12 explanation)
  - Contact first_name / job_title
  - Company name / industry

Pluggable provider pattern (mirrors File 09/10/11/12):
    set_default_outreach_generator(fake)   # for tests
    get_default_outreach_generator()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


# --- Status taxonomy --------------------------------------------------------

OUTREACH_STATUSES = ("draft", "approved", "sent")
OUTREACH_CHANNELS = ("email",)
PRIORITY_TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def tier_meets_min(tier: Optional[str], min_tier: str) -> bool:
    """A meets B (min_tier=B), C does not meet B."""
    if not tier:
        return False
    return PRIORITY_TIER_ORDER.get(tier.upper(), 99) <= PRIORITY_TIER_ORDER.get(
        min_tier.upper(), 99
    )


# --- Helpers ----------------------------------------------------------------

def _norm(s: Any) -> str:
    return str(s or "").strip()


def _signal_phrase(signal_type: str) -> str:
    """Map a signal_type to a friendly phrase used inside the email body."""
    mapping = {
        "hiring_intent":      "I noticed you're hiring",
        "hiring_pace":        "I saw your hiring pace pick up recently",
        "funding":            "Congrats on the recent funding news",
        "tech_stack_change":  "I noticed a recent change in your tech stack",
        "news_mention":       "I saw a recent press mention about your team",
        "social_activity":    "I noticed your team has been active publicly",
        "role_change":        "Congrats on the recent role change",
        "linkedin_activity":  "I saw your team's recent LinkedIn activity",
    }
    return mapping.get(signal_type, f"I noticed signal: {signal_type}")


def _top_signal_contributions(explanation: Optional[dict], n: int = 3) -> list[dict]:
    """Return the top-N signal contributions from a File-12 scoring_explanation.

    Falls back to an empty list when no explanation / contributions are present.
    """
    if not explanation or not isinstance(explanation, dict):
        return []
    intent = explanation.get("intent") or {}
    contribs = intent.get("contributions") or []
    if not isinstance(contribs, list):
        return []
    sorted_c = sorted(
        contribs,
        key=lambda c: float(c.get("contribution") or 0.0),
        reverse=True,
    )
    out: list[dict] = []
    seen_types: set[str] = set()
    for c in sorted_c:
        st = str(c.get("signal_type") or "")
        if not st or st in seen_types:
            continue
        seen_types.add(st)
        out.append(c)
        if len(out) >= n:
            break
    return out


def _matched_criteria(explanation: Optional[dict]) -> list[str]:
    if not explanation or not isinstance(explanation, dict):
        return []
    fit = explanation.get("fit") or {}
    matched = fit.get("matched") or []
    return [str(x) for x in matched if x]


def _icp_pain_points(icp: dict) -> list[str]:
    pp = icp.get("pain_points")
    if not pp:
        return []
    if isinstance(pp, str):
        return [pp]
    if isinstance(pp, list):
        return [str(x).strip() for x in pp if str(x).strip()]
    return []


def _render_prompt(
    *,
    icp: dict,
    lead: dict,
    contact: Optional[dict],
    company: dict,
    signals_top: list[dict],
    matched_criteria: list[str],
    channel: str = "email",
) -> str:
    """Build a deterministic prompt string sent to the LLM.

    Persisted on the outreach_messages row for traceability.
    """
    contact_name = _norm((contact or {}).get("first_name")) or _norm(
        (contact or {}).get("full_name")
    ) or "there"
    job_title = _norm((contact or {}).get("job_title")) or "the team"
    company_name = _norm(company.get("name")) or _norm(company.get("domain")) or "your company"
    industry = _norm(company.get("industry")) or "your industry"
    value_prop = _norm(icp.get("value_proposition")) or "we help teams move faster"
    outreach_angle = _norm(icp.get("outreach_angle")) or value_prop
    pains = _icp_pain_points(icp)
    pains_blob = "; ".join(pains[:3]) if pains else "(no pain points provided)"

    sig_lines = []
    for c in signals_top:
        st = str(c.get("signal_type") or "")
        sig_lines.append(f"- {st} (strength={c.get('strength')}, recency={c.get('recency')}): {_signal_phrase(st)}")
    sig_blob = "\n".join(sig_lines) if sig_lines else "(no signals available)"

    matched_blob = ", ".join(matched_criteria) if matched_criteria else "(no fit criteria)"

    prompt = (
        f"You are writing a {channel} cold outreach to {contact_name} ({job_title}) at "
        f"{company_name} (industry: {industry}).\n"
        f"ICP value proposition: {value_prop}\n"
        f"Outreach angle: {outreach_angle}\n"
        f"ICP pain points: {pains_blob}\n"
        f"Lead fit criteria matched: {matched_blob}\n"
        f"Top recent signals about this account:\n{sig_blob}\n"
        f"Constraints: <=120 words, plain prose, one specific reference to a signal, "
        f"end with a single low-friction question. Return JSON: "
        f'{{"subject": str, "body": str, "body_html": str|null}}.'
    )
    return prompt


def _token_counts(usage: Any) -> tuple[int, int]:
    """Best-effort split of total tokens into (prompt, completion).

    `vtlib.openaillm.OpenaiLLM.call_openai_tools` returns {"tokens": total}.
    We split 60/40 as a heuristic when only the total is available.
    """
    if not usage:
        return 0, 0
    if isinstance(usage, dict):
        if "prompt_tokens" in usage or "completion_tokens" in usage:
            return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        total = int(usage.get("tokens") or usage.get("total_tokens") or 0)
        if total <= 0:
            return 0, 0
        prompt_t = int(round(total * 0.6))
        return prompt_t, max(0, total - prompt_t)
    return 0, 0


# --- Result dataclass -------------------------------------------------------

@dataclass
class OutreachResult:
    subject: str
    body: str
    body_html: Optional[str] = None
    model: str = "fake"
    prompt: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    context: dict = field(default_factory=dict)
    raw_response: dict = field(default_factory=dict)


# --- Provider Protocol + Implementations ------------------------------------

class OutreachGenerator(Protocol):
    def generate(
        self,
        *,
        icp: dict,
        lead: dict,
        contact: Optional[dict],
        company: dict,
        signals_top: list[dict],
        matched_criteria: list[str],
        channel: str = "email",
    ) -> OutreachResult: ...


@dataclass
class LLMOutreachGenerator:
    """Real LLM-backed generator using vtlib.openaillm.OpenaiLLM-compatible client.

    Expects an injected `llm` object with a `call_openai_tools(messages, ..., response_format='json')`
    that returns (response_dict, usage_dict). Defaults to None — caller must inject.
    """
    llm: Any = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.3

    def generate(
        self, *, icp: dict, lead: dict, contact: Optional[dict],
        company: dict, signals_top: list[dict], matched_criteria: list[str],
        channel: str = "email",
    ) -> OutreachResult:
        prompt = _render_prompt(
            icp=icp, lead=lead, contact=contact, company=company,
            signals_top=signals_top, matched_criteria=matched_criteria, channel=channel,
        )
        if self.llm is None:
            # No LLM client wired — degrade to a deterministic stub so persistence
            # still has something usable, but flag the model as 'llm_unavailable'.
            stub_subject = (
                f"Quick thought for {_norm((contact or {}).get('first_name')) or _norm(company.get('name')) or 'you'}"
            )
            return OutreachResult(
                subject=stub_subject,
                body=f"Hi {_norm((contact or {}).get('first_name')) or 'there'},\n\nLLM is not configured.\n\n— Outreach stub",
                body_html=None,
                model="llm_unavailable",
                prompt=prompt,
                prompt_tokens=0,
                completion_tokens=0,
                context={
                    "signals_top": signals_top,
                    "matched_criteria": matched_criteria,
                    "channel": channel,
                },
                raw_response={"note": "llm_not_configured"},
            )
        messages = [
            {"role": "system", "content": "You write concise, specific B2B cold emails. Output strict JSON."},
            {"role": "user", "content": prompt},
        ]
        try:
            payload, usage = self.llm.call_openai_tools(
                messages, llm_model=self.model, temperature=self.temperature,
                response_format="json",
            )
        except Exception as e:
            payload, usage = (
                {"subject": "Quick thought", "body": f"(LLM error: {e})", "body_html": None},
                {"tokens": 0},
            )
        payload = payload or {}
        prompt_t, completion_t = _token_counts(usage)
        return OutreachResult(
            subject=str(payload.get("subject") or "Quick thought"),
            body=str(payload.get("body") or ""),
            body_html=payload.get("body_html") or None,
            model=self.model,
            prompt=prompt,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            context={
                "signals_top": signals_top,
                "matched_criteria": matched_criteria,
                "channel": channel,
            },
            raw_response=payload if isinstance(payload, dict) else {"raw": str(payload)},
        )


@dataclass
class FakeOutreachGenerator:
    """Deterministic generator for tests. Composes subject/body from inputs.

    Embeds: contact first_name, company name, ICP value_proposition,
    one signal phrase from the top contribution.
    """
    fixed_subject: Optional[str] = None
    fixed_body: Optional[str] = None
    model: str = "fake-outreach-1"

    def generate(
        self, *, icp: dict, lead: dict, contact: Optional[dict],
        company: dict, signals_top: list[dict], matched_criteria: list[str],
        channel: str = "email",
    ) -> OutreachResult:
        prompt = _render_prompt(
            icp=icp, lead=lead, contact=contact, company=company,
            signals_top=signals_top, matched_criteria=matched_criteria, channel=channel,
        )
        first_name = _norm((contact or {}).get("first_name")) or "there"
        company_name = _norm(company.get("name")) or _norm(company.get("domain")) or "your team"
        value_prop = _norm(icp.get("value_proposition")) or "help teams move faster"
        sig_phrase = _signal_phrase(signals_top[0]["signal_type"]) if signals_top else "I came across your company"
        subject = self.fixed_subject or f"{value_prop[:60]} — quick thought for {company_name}"
        body = self.fixed_body or (
            f"Hi {first_name},\n\n"
            f"{sig_phrase} at {company_name}. "
            f"Many {_norm(company.get('industry')) or 'similar'} teams use us to {value_prop.lower()}. "
            f"Worth a 15-min chat next week?\n\n"
            f"— Outreach"
        )
        return OutreachResult(
            subject=subject,
            body=body,
            body_html=None,
            model=self.model,
            prompt=prompt,
            prompt_tokens=len(prompt) // 4,
            completion_tokens=len(body) // 4,
            context={
                "signals_top": signals_top,
                "matched_criteria": matched_criteria,
                "channel": channel,
            },
            raw_response={"subject": subject, "body": body},
        )


# --- Module-level pluggable provider ---------------------------------------

_default_generator: OutreachGenerator = LLMOutreachGenerator()


def get_default_outreach_generator() -> OutreachGenerator:
    return _default_generator


def set_default_outreach_generator(gen: Optional[OutreachGenerator]) -> None:
    global _default_generator
    _default_generator = gen if gen is not None else LLMOutreachGenerator()


def generate_outreach(
    *, icp: dict, lead: dict, contact: Optional[dict], company: dict,
    signals_top: list[dict], matched_criteria: list[str],
    channel: str = "email",
    generator: Optional[OutreachGenerator] = None,
) -> OutreachResult:
    return (generator or _default_generator).generate(
        icp=icp, lead=lead, contact=contact, company=company,
        signals_top=signals_top, matched_criteria=matched_criteria, channel=channel,
    )
