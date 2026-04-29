"""Company enrichment service.

Given a company (with a domain), fetch the homepage, extract meta + tech stack,
persist a `company_enrichment` snapshot, and merge inferred fields back into
the `companies` row (industry, description, ecommerce_platform, tech_stack).

Pure logic helpers (extract_meta, detect_tech_stack) are network-free and
unit-testable on raw HTML strings.
"""
from __future__ import annotations

import html as html_mod
import re
from typing import Any

from services.website_fetcher import (
    FetchResult, Fetcher, fetch_homepage, get_default_fetcher,
)


PROVIDER = "website_homepage"

# ---------------------------------------------------------------------------
# Tech-stack signatures (string-in-html-or-headers checks; lowercase compare)
# ---------------------------------------------------------------------------
ECOMMERCE_PLATFORMS = ("shopify", "woocommerce", "bigcommerce", "magento", "prestashop")

TECH_SIGNATURES: dict[str, tuple[str, ...]] = {
    "Shopify": ("cdn.shopify.com", "shopify.theme", "/shopifycloud/", "x-shopify-stage", "myshopify.com"),
    "WooCommerce": ("woocommerce", "wp-content/plugins/woocommerce", "wc-blocks"),
    "BigCommerce": ("cdn11.bigcommerce.com", "bigcommerce.com/s-"),
    "Magento": ("mage/cookies", "magento", "/static/version"),
    "PrestaShop": ("prestashop", "var prestashop"),
    "Klaviyo": ("static.klaviyo.com", "klaviyo.js", "_learnq"),
    "Omnisend": ("omnisend.com", "omnisnippet1.com", "omnisend"),
    "Mailchimp": ("chimpstatic.com", "mc.us", "mailchimp"),
    "HubSpot": ("js.hs-scripts.com", "hs-analytics", "_hsq", "hubspot"),
    "Meta Pixel": ("connect.facebook.net/en_us/fbevents.js", "fbq(", "facebook pixel"),
    "Gorgias": ("config.gorgias.chat", "gorgias-chat", "gorgias.io"),
    "Recharge": ("rechargepayments.com", "rechargecdn.com", "recharge-checkout"),
    "Google Analytics": ("googletagmanager.com/gtag/js", "google-analytics.com/analytics.js", "ga('create'"),
    "Google Tag Manager": ("googletagmanager.com/gtm.js", "gtm-"),
    "Stripe": ("js.stripe.com",),
    "Intercom": ("widget.intercom.io", "intercomsettings"),
}


# ---------------------------------------------------------------------------
# HTML extraction helpers (no external deps)
# ---------------------------------------------------------------------------
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"""([a-zA-Z:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _attrs(tag: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR_RE.finditer(tag):
        name = (m.group(1) or "").lower()
        val = m.group(2) or m.group(3) or m.group(4) or ""
        out[name] = html_mod.unescape(val)
    return out


def extract_meta(html: str) -> dict[str, Any]:
    """Return {title, description, og_title, og_description, og_image, og_site_name,
    canonical, language, social_links}."""
    out: dict[str, Any] = {
        "title": None, "description": None,
        "og_title": None, "og_description": None, "og_image": None, "og_site_name": None,
        "canonical": None, "language": None,
        "social_links": [],
    }
    if not html:
        return out

    m = _TITLE_RE.search(html)
    if m:
        out["title"] = _WHITESPACE_RE.sub(" ", html_mod.unescape(m.group(1))).strip() or None

    # <html lang="en">
    m_html = re.search(r"<html\b[^>]*>", html, flags=re.IGNORECASE)
    if m_html:
        attrs = _attrs(m_html.group(0))
        if "lang" in attrs:
            out["language"] = attrs["lang"].strip().lower() or None

    for tag in _META_RE.findall(html):
        a = _attrs(tag)
        name = (a.get("name") or "").lower()
        prop = (a.get("property") or "").lower()
        content = a.get("content")
        if not content:
            continue
        if name == "description" and not out["description"]:
            out["description"] = content.strip()
        elif prop == "og:title":
            out["og_title"] = content.strip()
        elif prop == "og:description":
            out["og_description"] = content.strip()
        elif prop == "og:image":
            out["og_image"] = content.strip()
        elif prop == "og:site_name":
            out["og_site_name"] = content.strip()

    # canonical link
    m_can = re.search(r'<link\b[^>]*rel\s*=\s*["\']canonical["\'][^>]*>', html, flags=re.IGNORECASE)
    if m_can:
        a = _attrs(m_can.group(0))
        if a.get("href"):
            out["canonical"] = a["href"].strip()

    # social links found in anchor hrefs
    socials: list[str] = []
    for m_a in re.finditer(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        href = m_a.group(1).strip()
        low = href.lower()
        if any(d in low for d in (
            "linkedin.com/", "twitter.com/", "x.com/", "facebook.com/",
            "instagram.com/", "youtube.com/", "tiktok.com/",
        )):
            if href not in socials:
                socials.append(href)
        if len(socials) >= 12:
            break
    out["social_links"] = socials
    return out


def extract_visible_text(html: str, max_chars: int = 4000) -> str:
    if not html:
        return ""
    cleaned = _SCRIPT_STYLE_RE.sub(" ", html)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = html_mod.unescape(cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:max_chars]


def detect_tech_stack(html: str, headers: dict[str, str] | None = None) -> tuple[list[str], str | None]:
    """Return (tech_stack, ecommerce_platform_or_none)."""
    if not html and not headers:
        return [], None
    haystack = (html or "").lower()
    if headers:
        # Append header keys+values for X-Shopify-* style checks
        for k, v in headers.items():
            haystack += " " + str(k).lower() + ": " + str(v).lower()
    found: list[str] = []
    for tech, sigs in TECH_SIGNATURES.items():
        for sig in sigs:
            if sig in haystack:
                found.append(tech)
                break
    ecom: str | None = None
    for tech in found:
        if tech.lower() in ECOMMERCE_PLATFORMS:
            ecom = tech.lower()
            break
    return found, ecom


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _merge_company_updates(existing: dict, snapshot: dict) -> dict:
    """Patch fields on companies when missing/empty; union tech_stack."""
    out: dict = {}
    if not (existing.get("description") or "").strip() and snapshot.get("description"):
        out["description"] = snapshot["description"]
    if not (existing.get("industry") or "").strip() and snapshot.get("industry"):
        out["industry"] = snapshot["industry"]
    if not (existing.get("ecommerce_platform") or "").strip() and snapshot.get("ecommerce_platform"):
        out["ecommerce_platform"] = snapshot["ecommerce_platform"]
    cur_stack = existing.get("tech_stack") or []
    if not isinstance(cur_stack, list):
        cur_stack = [cur_stack]
    inc_stack = snapshot.get("tech_stack") or []
    if inc_stack:
        seen = {str(x).lower(): x for x in cur_stack}
        merged = list(cur_stack)
        for item in inc_stack:
            if str(item).lower() not in seen:
                seen[str(item).lower()] = item
                merged.append(item)
        if merged != cur_stack:
            out["tech_stack"] = merged
    if existing.get("status") in (None, "", "new"):
        out["status"] = "enriched"
    return out


def build_snapshot_from_fetch(fetch: FetchResult) -> dict[str, Any]:
    """Pure: turn a FetchResult into an enrichment snapshot dict (no DB)."""
    meta = extract_meta(fetch.html)
    tech, ecom = detect_tech_stack(fetch.html, fetch.headers)
    text = extract_visible_text(fetch.html)
    desc = meta.get("description") or meta.get("og_description") or None
    if desc:
        desc = desc.strip()[:1000]
    snapshot = {
        "fetch_url": fetch.url,
        "status_code": fetch.status_code,
        "ok": bool(fetch.ok),
        "error": fetch.error,
        "title": meta.get("title"),
        "description": desc,
        "og_title": meta.get("og_title"),
        "og_description": meta.get("og_description"),
        "og_image": meta.get("og_image"),
        "og_site_name": meta.get("og_site_name"),
        "canonical": meta.get("canonical"),
        "language": meta.get("language"),
        "tech_stack": tech,
        "ecommerce_platform": ecom,
        "industry": None,  # left to richer providers later
        "social_links": meta.get("social_links") or [],
        "text_excerpt": text[:1500],
    }
    return snapshot


def enrich_company(
    repos,
    *,
    company_id: int,
    fetcher: Fetcher | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fetch homepage + extract + persist enrichment row + patch companies.

    Returns: {company_id, ok, status_code, snapshot, enrichment_id?, updates,
              skipped?, error?, dry_run}
    """
    company = repos.companies.get(company_id)
    if not company:
        return {"company_id": company_id, "ok": False, "skipped": True,
                "error": "company_not_found", "dry_run": dry_run}
    domain = company.get("domain")
    if not domain:
        return {"company_id": company_id, "ok": False, "skipped": True,
                "error": "company_missing_domain", "dry_run": dry_run}

    fetch = fetch_homepage(domain, fetcher or get_default_fetcher())
    snapshot = build_snapshot_from_fetch(fetch)
    updates = _merge_company_updates(company, snapshot) if snapshot.get("ok") else {}

    result: dict[str, Any] = {
        "company_id": company_id,
        "domain": domain,
        "ok": snapshot["ok"],
        "status_code": snapshot["status_code"],
        "error": snapshot.get("error"),
        "snapshot": snapshot,
        "updates": updates,
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    enrichment_id = repos.company_enrichment.create({
        "company_id": company_id,
        "provider": PROVIDER,
        "industry": snapshot.get("industry"),
        "tech_stack": snapshot.get("tech_stack") or [],
        "ecommerce_platform": snapshot.get("ecommerce_platform"),
        "social_links": snapshot.get("social_links") or [],
        "raw_data": snapshot,
        "confidence_score": 0.6 if snapshot["ok"] else 0.0,
    })
    result["enrichment_id"] = int(enrichment_id)

    if updates:
        repos.companies.update(company_id, updates)

    return result


def enrich_companies_batch(
    repos,
    *,
    project_id: int | None = None,
    company_ids: list[int] | None = None,
    limit: int = 50,
    only_missing: bool = True,
    fetcher: Fetcher | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Enrich a batch of companies.

    Selection order:
      1. explicit company_ids list (if provided), else
      2. project_id-scoped companies via lead_candidates JOIN, else
      3. all companies.
    If only_missing=True, skips companies that already have a company_enrichment row.
    """
    ids: list[int] = []
    if company_ids:
        ids = [int(x) for x in company_ids][:limit]
    elif project_id is not None:
        rows = repos.companies.storage.fetchall(
            "SELECT DISTINCT c.id FROM companies c "
            "JOIN lead_candidates lc ON lc.company_id = c.id "
            "WHERE lc.project_id = ? "
            "ORDER BY c.id ASC LIMIT ?",
            (int(project_id), int(limit)),
        )
        ids = [int(r["id"]) for r in rows]
    else:
        rows = repos.companies.storage.fetchall(
            "SELECT id FROM companies ORDER BY id ASC LIMIT ?", (int(limit),),
        )
        ids = [int(r["id"]) for r in rows]

    enriched: list[dict] = []
    skipped = 0
    failed = 0
    for cid in ids:
        if only_missing and repos.company_enrichment.exists({"company_id": cid}):
            skipped += 1
            continue
        try:
            res = enrich_company(repos, company_id=cid, fetcher=fetcher, dry_run=dry_run)
        except Exception as e:  # noqa: BLE001
            failed += 1
            enriched.append({"company_id": cid, "ok": False, "error": str(e)})
            continue
        if not res.get("ok"):
            failed += 1
        enriched.append(res)

    return {
        "scanned": len(ids),
        "enriched": sum(1 for r in enriched if r.get("ok")),
        "skipped": skipped,
        "failed": failed,
        "results": enriched,
        "dry_run": dry_run,
    }
