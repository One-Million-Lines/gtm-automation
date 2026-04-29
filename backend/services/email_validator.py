"""Email validator.

Pluggable validator with:
  - syntax check (RFC-ish regex)
  - free-mailbox / disposable / role-based / catch-all detection
  - domain MX validation (best-effort via dnspython if available, else socket A-record fallback)
  - in-process LRU cache for MX lookups

Public:
    EmailValidator           — Protocol
    DnsEmailValidator        — production validator (uses optional dnspython)
    FakeEmailValidator       — deterministic in-memory validator for tests
    ValidateResult           — dataclass with canonical fields
    set_default_validator / get_default_validator
    validate_email(email)    — convenience wrapper using default validator

Email status taxonomy (string values written to contacts.email_status):
    valid       — syntax OK, domain has MX (or known free provider), not disposable, not role
    risky       — catch-all hint, role-based mailbox, or low-confidence MX
    role        — role-based mailbox (info@, support@, ...) takes precedence over `risky`
    disposable  — disposable / throwaway provider
    invalid     — bad syntax OR domain has no MX / does not resolve
    unverified  — checks could not run (no validator wired, transient DNS error, etc.)
"""
from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass, field
from typing import Protocol


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EMAIL_SYNTAX_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

FREE_PROVIDERS = frozenset({
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.fr", "yahoo.de", "ymail.com",
    "hotmail.com", "outlook.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me",
    "gmx.com", "gmx.de", "gmx.net",
    "mail.com", "zoho.com", "yandex.com", "yandex.ru",
})

DISPOSABLE_PROVIDERS = frozenset({
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "trashmail.com", "yopmail.com", "fakeinbox.com", "throwaway.email",
    "maildrop.cc", "sharklasers.com", "getnada.com", "dispostable.com",
})

ROLE_LOCAL_PARTS = frozenset({
    "info", "contact", "support", "help", "sales", "admin", "office",
    "hello", "hi", "team", "noreply", "no-reply", "mail", "postmaster",
    "webmaster", "abuse", "billing", "press", "marketing", "jobs", "careers",
    "hr", "legal", "privacy", "security", "feedback", "general",
})

# Simple typo correction for very common typos (intentionally narrow).
COMMON_TYPO_FIXES: dict[str, str] = {
    "gmial.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gnail.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "yaho.com": "yahoo.com",
    "yhaoo.com": "yahoo.com",
    "hotnail.com": "hotmail.com",
    "hotmial.com": "hotmail.com",
    "outlok.com": "outlook.com",
    "iclould.com": "icloud.com",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class ValidateResult:
    email: str | None
    normalized: str | None
    syntax_ok: bool
    domain: str | None
    is_free: bool = False
    is_disposable: bool = False
    is_role: bool = False
    has_mx: bool | None = None       # True / False / None=unverified
    is_catch_all: bool | None = None
    typo_corrected: str | None = None  # original local-part lookup that we fixed
    status: str = "unverified"        # valid|risky|role|disposable|invalid|unverified
    confidence: float = 0.0
    reason: str = ""
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "normalized": self.normalized,
            "syntax_ok": self.syntax_ok,
            "domain": self.domain,
            "is_free": self.is_free,
            "is_disposable": self.is_disposable,
            "is_role": self.is_role,
            "has_mx": self.has_mx,
            "is_catch_all": self.is_catch_all,
            "typo_corrected": self.typo_corrected,
            "status": self.status,
            "confidence": self.confidence,
            "reason": self.reason,
            "raw": self.raw,
        }


# ---------------------------------------------------------------------------
# Helpers (pure)
# ---------------------------------------------------------------------------
def normalize_email(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip().lower()
    return s or None


def split_email(addr: str) -> tuple[str, str] | None:
    if "@" not in addr:
        return None
    local, _, domain = addr.partition("@")
    if not local or not domain:
        return None
    return local, domain


def maybe_fix_typo(domain: str) -> tuple[str, str | None]:
    """Return (corrected_domain, original_typo_or_None)."""
    fix = COMMON_TYPO_FIXES.get(domain)
    if fix:
        return fix, domain
    return domain, None


def is_free_provider(domain: str) -> bool:
    return domain in FREE_PROVIDERS


def is_disposable_provider(domain: str) -> bool:
    return domain in DISPOSABLE_PROVIDERS


def is_role_local(local: str) -> bool:
    return local.lower() in ROLE_LOCAL_PARTS


def classify(
    *,
    syntax_ok: bool,
    has_mx: bool | None,
    is_disposable: bool,
    is_role: bool,
    is_free: bool,
    is_catch_all: bool | None,
) -> tuple[str, float, str]:
    """Map all signals to (status, confidence, reason)."""
    if not syntax_ok:
        return "invalid", 0.0, "bad_syntax"
    if is_disposable:
        return "disposable", 0.2, "disposable_provider"
    if has_mx is False:
        return "invalid", 0.0, "no_mx"
    if is_role:
        # role-based — only weakly usable; mark as role explicitly
        if has_mx is None:
            return "role", 0.4, "role_local_part"
        return "role", 0.5, "role_local_part"
    if is_catch_all:
        return "risky", 0.5, "catch_all"
    if has_mx is True:
        if is_free:
            return "valid", 0.8, "free_provider_mx_ok"
        return "valid", 0.9, "mx_ok"
    # has_mx is None
    if is_free:
        # Free providers are stable — treat MX as implicit ok with mid confidence.
        return "valid", 0.7, "free_provider_assumed_mx"
    return "unverified", 0.3, "mx_unverified"


# ---------------------------------------------------------------------------
# Validator interface
# ---------------------------------------------------------------------------
class EmailValidator(Protocol):
    def validate(self, email: str | None) -> ValidateResult: ...


# ---------------------------------------------------------------------------
# DNS-backed validator (production)
# ---------------------------------------------------------------------------
class DnsEmailValidator:
    """Best-effort production validator.

    MX lookup path:
      1. dnspython if available (`dns.resolver.resolve(domain, "MX")`)
      2. fallback: socket.getaddrinfo on the domain (A-record exists -> assume MX-ish)
    Free providers short-circuit to has_mx=True.
    Catch-all: not detected here (would require SMTP probing) — left as None.
    """

    def __init__(self, dns_timeout: float = 3.0, cache_ttl_s: float = 600.0) -> None:
        self.dns_timeout = dns_timeout
        self.cache_ttl_s = cache_ttl_s
        self._mx_cache: dict[str, tuple[float, bool | None]] = {}

    # -- MX cache -----------------------------------------------------------
    def _cached_mx(self, domain: str) -> bool | None:
        hit = self._mx_cache.get(domain)
        if not hit:
            return None
        ts, val = hit
        if (time.time() - ts) > self.cache_ttl_s:
            self._mx_cache.pop(domain, None)
            return None
        return val

    def _store_mx(self, domain: str, val: bool | None) -> None:
        self._mx_cache[domain] = (time.time(), val)

    def _lookup_mx(self, domain: str) -> bool | None:
        # Try dnspython
        try:
            import dns.resolver  # type: ignore
            try:
                answers = dns.resolver.resolve(domain, "MX", lifetime=self.dns_timeout)
                return bool(list(answers))
            except dns.resolver.NoAnswer:
                # No MX, but domain exists — try A record fallback below.
                pass
            except dns.resolver.NXDOMAIN:
                return False
            except Exception:  # noqa: BLE001
                pass
        except ImportError:
            pass
        # Fallback: socket A-record check
        try:
            socket.setdefaulttimeout(self.dns_timeout)
            socket.gethostbyname(domain)
            return True
        except OSError:
            return False
        except Exception:  # noqa: BLE001
            return None

    def lookup_mx(self, domain: str) -> bool | None:
        cached = self._cached_mx(domain)
        if cached is not None or domain in self._mx_cache:
            return self._mx_cache[domain][1]
        val = self._lookup_mx(domain)
        self._store_mx(domain, val)
        return val

    # -- main validate ------------------------------------------------------
    def validate(self, email: str | None) -> ValidateResult:
        norm = normalize_email(email)
        if not norm or not EMAIL_SYNTAX_RE.match(norm):
            return ValidateResult(
                email=email, normalized=norm, syntax_ok=False, domain=None,
                status="invalid", confidence=0.0, reason="bad_syntax",
            )
        parts = split_email(norm)
        assert parts is not None
        local, domain = parts
        domain, typo_orig = maybe_fix_typo(domain)
        if typo_orig:
            norm = f"{local}@{domain}"

        is_disp = is_disposable_provider(domain)
        is_free = is_free_provider(domain)
        is_role_v = is_role_local(local)

        if is_free or is_disp:
            has_mx: bool | None = True if is_free else False if is_disp else None
        else:
            has_mx = self.lookup_mx(domain)

        status, conf, reason = classify(
            syntax_ok=True, has_mx=has_mx, is_disposable=is_disp,
            is_role=is_role_v, is_free=is_free, is_catch_all=None,
        )
        return ValidateResult(
            email=email, normalized=norm, syntax_ok=True, domain=domain,
            is_free=is_free, is_disposable=is_disp, is_role=is_role_v,
            has_mx=has_mx, is_catch_all=None,
            typo_corrected=typo_orig,
            status=status, confidence=conf, reason=reason,
        )


# ---------------------------------------------------------------------------
# Fake validator for tests
# ---------------------------------------------------------------------------
class FakeEmailValidator:
    """In-memory validator. Configure per-domain MX state and per-email overrides."""

    def __init__(
        self,
        *,
        domains_with_mx: set[str] | None = None,
        domains_without_mx: set[str] | None = None,
        catch_all_domains: set[str] | None = None,
        overrides: dict[str, ValidateResult] | None = None,
    ) -> None:
        self.with_mx = set(domains_with_mx or set())
        self.without_mx = set(domains_without_mx or set())
        self.catch_all = set(catch_all_domains or set())
        self.overrides = dict(overrides or {})
        self.calls: list[str] = []

    def validate(self, email: str | None) -> ValidateResult:
        self.calls.append(email or "")
        norm = normalize_email(email)
        if norm and norm in self.overrides:
            r = self.overrides[norm]
            # Always echo the original input on the result.
            return ValidateResult(**{**r.to_dict(), "email": email, "normalized": norm})

        if not norm or not EMAIL_SYNTAX_RE.match(norm):
            return ValidateResult(
                email=email, normalized=norm, syntax_ok=False, domain=None,
                status="invalid", confidence=0.0, reason="bad_syntax",
            )
        parts = split_email(norm)
        assert parts is not None
        local, domain = parts
        domain, typo_orig = maybe_fix_typo(domain)
        if typo_orig:
            norm = f"{local}@{domain}"

        is_disp = is_disposable_provider(domain)
        is_free = is_free_provider(domain)
        is_role_v = is_role_local(local)

        if is_free:
            has_mx: bool | None = True
        elif is_disp:
            has_mx = False
        elif domain in self.with_mx:
            has_mx = True
        elif domain in self.without_mx:
            has_mx = False
        else:
            has_mx = None

        catch = True if domain in self.catch_all else None
        status, conf, reason = classify(
            syntax_ok=True, has_mx=has_mx, is_disposable=is_disp,
            is_role=is_role_v, is_free=is_free, is_catch_all=catch,
        )
        return ValidateResult(
            email=email, normalized=norm, syntax_ok=True, domain=domain,
            is_free=is_free, is_disposable=is_disp, is_role=is_role_v,
            has_mx=has_mx, is_catch_all=catch,
            typo_corrected=typo_orig,
            status=status, confidence=conf, reason=reason,
        )


# ---------------------------------------------------------------------------
# Default validator wiring
# ---------------------------------------------------------------------------
_default_validator: EmailValidator = DnsEmailValidator()


def set_default_validator(v: EmailValidator) -> None:
    global _default_validator
    _default_validator = v


def get_default_validator() -> EmailValidator:
    return _default_validator


def validate_email(email: str | None, validator: EmailValidator | None = None) -> ValidateResult:
    return (validator or _default_validator).validate(email)
