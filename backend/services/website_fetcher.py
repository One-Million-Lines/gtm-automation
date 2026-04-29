"""Website fetcher.

Fetches the homepage HTML for a domain. Pluggable so tests can inject a fake
in-memory fetcher without touching the network.

Public:
    Fetcher                — Protocol-style abstract fetcher.
    HttpFetcher            — real urllib-based fetcher (used in production).
    FakeFetcher            — in-memory dict-driven fetcher (tests).
    FetchResult            — {url, status_code, html, headers, error}
    fetch_homepage(domain) — convenience wrapper using the default fetcher.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


DEFAULT_TIMEOUT = 8.0
DEFAULT_USER_AGENT = "GTMBot/0.1 (+https://onemillionlines.com)"
MAX_HTML_BYTES = 800_000  # ~800KB cap


@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str
    headers: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status_code < 400 and bool(self.html)


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


class HttpFetcher:
    """Real fetcher (urllib, no extra deps)."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch(self, url: str) -> FetchResult:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(MAX_HTML_BYTES + 1)
                if len(raw) > MAX_HTML_BYTES:
                    raw = raw[:MAX_HTML_BYTES]
                ctype = resp.headers.get("Content-Type", "") or ""
                charset = "utf-8"
                if "charset=" in ctype.lower():
                    charset = ctype.lower().split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
                try:
                    html = raw.decode(charset, errors="replace")
                except LookupError:
                    html = raw.decode("utf-8", errors="replace")
                return FetchResult(
                    url=resp.geturl(),
                    status_code=resp.getcode() or 0,
                    html=html,
                    headers={k: v for k, v in resp.headers.items()},
                )
        except urllib.error.HTTPError as e:
            return FetchResult(url=url, status_code=e.code or 0, html="", error=f"http_error: {e}")
        except Exception as e:  # noqa: BLE001
            return FetchResult(url=url, status_code=0, html="", error=str(e))


class FakeFetcher:
    """In-memory fetcher for tests. Maps url-or-domain -> html (or FetchResult)."""

    def __init__(self, pages: dict[str, str | FetchResult] | None = None) -> None:
        self.pages: dict[str, str | FetchResult] = pages or {}
        self.calls: list[str] = []

    def add(self, key: str, html_or_result: str | FetchResult) -> None:
        self.pages[key] = html_or_result

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        # Try exact url, then domain key fallback
        keys = [url, url.rstrip("/"), url.replace("https://", "").replace("http://", "").rstrip("/")]
        for k in keys:
            if k in self.pages:
                v = self.pages[k]
                if isinstance(v, FetchResult):
                    return v
                return FetchResult(url=url, status_code=200, html=v)
            # Also try without leading www.
            stripped = k.removeprefix("www.")
            if stripped in self.pages:
                v = self.pages[stripped]
                if isinstance(v, FetchResult):
                    return v
                return FetchResult(url=url, status_code=200, html=v)
        return FetchResult(url=url, status_code=404, html="", error="not_found_in_fake_fetcher")


# Module-level default fetcher; tests can override via set_default_fetcher().
_default_fetcher: Fetcher = HttpFetcher()


def set_default_fetcher(fetcher: Fetcher) -> None:
    global _default_fetcher
    _default_fetcher = fetcher


def get_default_fetcher() -> Fetcher:
    return _default_fetcher


def fetch_homepage(domain: str, fetcher: Fetcher | None = None) -> FetchResult:
    f = fetcher or _default_fetcher
    url = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
    return f.fetch(url)
