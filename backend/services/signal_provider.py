"""Signal provider — pluggable detection of company/contact signals.

Public:
    SignalProvider              — Protocol; .extract_company / .extract_contact
    DetectedSignal              — dataclass {signal_type, signal_name, ...}
    HttpSignalProvider          — real provider (uses website_fetcher)
    FakeSignalProvider          — in-memory provider for tests
    set_default_signal_provider / get_default_signal_provider / extract_company_signals
    diff_tech_stack(prev, curr) — helper for tech-stack churn signals
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from services.website_fetcher import (
    FetchResult, Fetcher, get_default_fetcher,
)

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

SIGNAL_TYPES = {
    "hiring_intent",      # careers/jobs page hits
    "news_mention",       # press / news keywords
    "funding",            # funding-round mentions
    "tech_stack_change",  # delta vs previous enrichment
    "hiring_pace",        # employee_count delta
    "social_activity",    # bumps in known social links
    "role_change",        # contact-level: title/role updated
    "linkedin_activity",  # contact-level: LinkedIn activity proxy
}

CAREERS_PATHS = ("/careers", "/jobs", "/join", "/work-with-us", "/hiring")

NEWS_KEYWORDS = (
    "press release", "in the news", "newsroom", "media coverage",
    "announcement", "today announced", "named to", "wins award",
)

FUNDING_KEYWORDS = (
    "series a", "series b", "series c", "series d",
    "seed round", "raised $", "funding round", "led the round",
    "venture capital", "lead investor",
)

JOB_TITLE_HINTS_RE = re.compile(
    r"\b(engineer|developer|designer|manager|director|head\s+of|vp\s+of|"
    r"chief|cto|ceo|cmo|coo|cfo|founder|product|sales|marketing|recruit)\b",
    re.IGNORECASE,
)


@dataclass
class DetectedSignal:
    signal_type: str
    signal_name: str
    description: str = ""
    extracted_text: str | None = None
    source_url: str | None = None
    strength_score: float = 0.5
    confidence_score: float = 0.5
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_row(self, *, company_id: int | None, contact_id: int | None,
               icp_id: int | None, detected_by: str) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "contact_id": contact_id,
            "icp_id": icp_id,
            "signal_type": self.signal_type,
            "signal_name": self.signal_name,
            "description": self.description,
            "extracted_text": self.extracted_text,
            "source_url": self.source_url,
            "strength_score": float(self.strength_score),
            "confidence_score": float(self.confidence_score),
            "detected_by": detected_by,
            "raw_data": self.raw_data,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scan_keywords(html: str, keywords: Iterable[str]) -> list[str]:
    if not html:
        return []
    low = html.lower()
    return [kw for kw in keywords if kw in low]


def _count_jobs_in_html(html: str) -> int:
    if not html:
        return 0
    matches = JOB_TITLE_HINTS_RE.findall(html)
    return len(matches)


def diff_tech_stack(prev: list[str] | None, curr: list[str] | None) -> dict[str, list[str]]:
    p = set([t for t in (prev or []) if t])
    c = set([t for t in (curr or []) if t])
    return {"added": sorted(c - p), "removed": sorted(p - c)}


# ---------------------------------------------------------------------------
# Provider Protocol + Real impl
# ---------------------------------------------------------------------------

class SignalProvider(Protocol):
    def extract_company(
        self, *,
        company: dict[str, Any],
        latest_enrichment: dict[str, Any] | None = None,
        previous_enrichment: dict[str, Any] | None = None,
    ) -> list[DetectedSignal]: ...

    def extract_contact(
        self, *,
        contact: dict[str, Any],
        previous_contact: dict[str, Any] | None = None,
    ) -> list[DetectedSignal]: ...


def _domain_to_url(domain: str) -> str:
    if not domain:
        return ""
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain.rstrip("/")
    return f"https://{domain}".rstrip("/")


class HttpSignalProvider:
    """Real provider: uses website_fetcher for company-level web signals."""

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        self._fetcher = fetcher

    def _fetch(self, url: str) -> FetchResult:
        f = self._fetcher or get_default_fetcher()
        return f.fetch(url)

    def extract_company(
        self, *,
        company: dict[str, Any],
        latest_enrichment: dict[str, Any] | None = None,
        previous_enrichment: dict[str, Any] | None = None,
    ) -> list[DetectedSignal]:
        out: list[DetectedSignal] = []
        domain = (company.get("domain") or "").strip()
        base = _domain_to_url(domain)

        # 1. Hiring-intent — careers page
        if base:
            for path in CAREERS_PATHS:
                url = base + path
                fr = self._fetch(url)
                if fr.ok and fr.html:
                    job_count = _count_jobs_in_html(fr.html)
                    strength = min(1.0, 0.3 + 0.05 * job_count)
                    out.append(DetectedSignal(
                        signal_type="hiring_intent",
                        signal_name=f"careers_page:{path}",
                        description=f"Careers page reachable; ~{job_count} role hints",
                        source_url=url,
                        strength_score=strength,
                        confidence_score=0.7,
                        raw_data={"job_hint_count": job_count, "path": path},
                    ))
                    break

        # 2/3. News + funding from homepage
        homepage = self._fetch(base) if base else FetchResult(url="", status_code=0, html="")
        if homepage.ok and homepage.html:
            news_hits = _scan_keywords(homepage.html, NEWS_KEYWORDS)
            if news_hits:
                out.append(DetectedSignal(
                    signal_type="news_mention",
                    signal_name="homepage_news_keywords",
                    description=f"news/press keywords: {', '.join(news_hits[:3])}",
                    source_url=base,
                    strength_score=min(1.0, 0.3 + 0.15 * len(news_hits)),
                    confidence_score=0.5,
                    raw_data={"matches": news_hits},
                ))
            funding_hits = _scan_keywords(homepage.html, FUNDING_KEYWORDS)
            if funding_hits:
                out.append(DetectedSignal(
                    signal_type="funding",
                    signal_name="homepage_funding_keywords",
                    description=f"funding keywords: {', '.join(funding_hits[:3])}",
                    source_url=base,
                    strength_score=min(1.0, 0.4 + 0.2 * len(funding_hits)),
                    confidence_score=0.55,
                    raw_data={"matches": funding_hits},
                ))

        # 4. Tech-stack churn (delta between previous and latest enrichment)
        out.extend(_compute_tech_stack_change(latest_enrichment, previous_enrichment))

        # 5. Hiring-pace (employee_count delta)
        out.extend(_compute_hiring_pace(latest_enrichment, previous_enrichment))

        # 6. Social-activity bump (presence of new social links)
        out.extend(_compute_social_bump(latest_enrichment, previous_enrichment))

        return out

    def extract_contact(
        self, *,
        contact: dict[str, Any],
        previous_contact: dict[str, Any] | None = None,
    ) -> list[DetectedSignal]:
        out: list[DetectedSignal] = []

        # role_change — compare normalized_role/job_title to previous
        if previous_contact:
            prev_title = (previous_contact.get("job_title") or "").strip().lower()
            curr_title = (contact.get("job_title") or "").strip().lower()
            if prev_title and curr_title and prev_title != curr_title:
                out.append(DetectedSignal(
                    signal_type="role_change",
                    signal_name="job_title_changed",
                    description=f"{prev_title} → {curr_title}",
                    strength_score=0.7,
                    confidence_score=0.6,
                    raw_data={"from": prev_title, "to": curr_title},
                ))

        # linkedin_activity proxy — presence of LinkedIn URL recently updated
        li = (contact.get("linkedin_url") or "").strip()
        if li:
            out.append(DetectedSignal(
                signal_type="linkedin_activity",
                signal_name="linkedin_present",
                description="LinkedIn URL present (proxy for activity)",
                source_url=li,
                strength_score=0.3,
                confidence_score=0.3,
                raw_data={"linkedin_url": li},
            ))
        return out


# ---------------------------------------------------------------------------
# Pure helpers extracted so tests can call them without a provider
# ---------------------------------------------------------------------------

def _compute_tech_stack_change(
    latest: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> list[DetectedSignal]:
    if not latest or not previous:
        return []
    diff = diff_tech_stack(previous.get("tech_stack"), latest.get("tech_stack"))
    if not diff["added"] and not diff["removed"]:
        return []
    n = len(diff["added"]) + len(diff["removed"])
    return [DetectedSignal(
        signal_type="tech_stack_change",
        signal_name="tech_stack_diff",
        description=f"+{len(diff['added'])} / -{len(diff['removed'])} tech changes",
        strength_score=min(1.0, 0.3 + 0.2 * n),
        confidence_score=0.7,
        raw_data=diff,
    )]


def _compute_hiring_pace(
    latest: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> list[DetectedSignal]:
    if not latest or not previous:
        return []
    p = previous.get("employee_count")
    c = latest.get("employee_count")
    if p is None or c is None or p <= 0:
        return []
    delta = c - p
    if delta == 0:
        return []
    pct = delta / max(p, 1)
    if abs(pct) < 0.05:
        return []
    direction = "up" if delta > 0 else "down"
    return [DetectedSignal(
        signal_type="hiring_pace",
        signal_name=f"employee_count_{direction}",
        description=f"employee_count {p} → {c} ({pct:+.0%})",
        strength_score=min(1.0, 0.4 + abs(pct)),
        confidence_score=0.5,
        raw_data={"from": p, "to": c, "delta": delta, "pct": pct},
    )]


def _compute_social_bump(
    latest: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> list[DetectedSignal]:
    if not latest:
        return []
    prev_links = set(previous.get("social_links") or []) if previous else set()
    curr_links = set(latest.get("social_links") or [])
    new_links = sorted(curr_links - prev_links)
    if not new_links:
        return []
    return [DetectedSignal(
        signal_type="social_activity",
        signal_name="new_social_links",
        description=f"{len(new_links)} new social link(s)",
        strength_score=min(1.0, 0.3 + 0.1 * len(new_links)),
        confidence_score=0.4,
        raw_data={"new_links": new_links},
    )]


# ---------------------------------------------------------------------------
# FakeSignalProvider for tests
# ---------------------------------------------------------------------------

class FakeSignalProvider:
    """In-memory provider — return preconfigured signals per company/contact id."""

    def __init__(self) -> None:
        self.company_signals: dict[int, list[DetectedSignal]] = {}
        self.contact_signals: dict[int, list[DetectedSignal]] = {}
        self.company_calls: list[int] = []
        self.contact_calls: list[int] = []

    def for_company(self, company_id: int, signals: list[DetectedSignal]) -> None:
        self.company_signals[int(company_id)] = list(signals)

    def for_contact(self, contact_id: int, signals: list[DetectedSignal]) -> None:
        self.contact_signals[int(contact_id)] = list(signals)

    def extract_company(
        self, *,
        company: dict[str, Any],
        latest_enrichment: dict[str, Any] | None = None,
        previous_enrichment: dict[str, Any] | None = None,
    ) -> list[DetectedSignal]:
        cid = int(company.get("id") or 0)
        self.company_calls.append(cid)
        out = list(self.company_signals.get(cid, []))
        # Still apply the pure delta helpers so tests can verify churn detection.
        out.extend(_compute_tech_stack_change(latest_enrichment, previous_enrichment))
        out.extend(_compute_hiring_pace(latest_enrichment, previous_enrichment))
        out.extend(_compute_social_bump(latest_enrichment, previous_enrichment))
        return out

    def extract_contact(
        self, *,
        contact: dict[str, Any],
        previous_contact: dict[str, Any] | None = None,
    ) -> list[DetectedSignal]:
        cid = int(contact.get("id") or 0)
        self.contact_calls.append(cid)
        return list(self.contact_signals.get(cid, []))


# ---------------------------------------------------------------------------
# Default-provider plumbing
# ---------------------------------------------------------------------------

_default_provider: SignalProvider = HttpSignalProvider()


def set_default_signal_provider(p: SignalProvider) -> None:
    global _default_provider
    _default_provider = p


def get_default_signal_provider() -> SignalProvider:
    return _default_provider


def extract_company_signals(
    *,
    company: dict[str, Any],
    latest_enrichment: dict[str, Any] | None = None,
    previous_enrichment: dict[str, Any] | None = None,
    provider: SignalProvider | None = None,
) -> list[DetectedSignal]:
    p = provider or _default_provider
    return p.extract_company(
        company=company,
        latest_enrichment=latest_enrichment,
        previous_enrichment=previous_enrichment,
    )


def extract_contact_signals(
    *,
    contact: dict[str, Any],
    previous_contact: dict[str, Any] | None = None,
    provider: SignalProvider | None = None,
) -> list[DetectedSignal]:
    p = provider or _default_provider
    return p.extract_contact(contact=contact, previous_contact=previous_contact)
