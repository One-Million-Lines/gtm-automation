"""Smoke test for File 09 — company enrichment module (no real network)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import pipeline_runner, repos
from services.enrichment_service import (
    build_snapshot_from_fetch, detect_tech_stack, enrich_companies_batch,
    enrich_company, extract_meta, extract_visible_text,
)
from services.website_fetcher import FakeFetcher, FetchResult, set_default_fetcher


SHOPIFY_HTML = """
<!doctype html>
<html lang="en">
<head>
  <title>Acme Co — Premium gear</title>
  <meta name="description" content="Acme sells premium widgets.">
  <meta property="og:title" content="Acme Co">
  <meta property="og:description" content="Premium widgets for everyone.">
  <meta property="og:image" content="https://acme.com/og.png">
  <meta property="og:site_name" content="Acme">
  <link rel="canonical" href="https://acme.com/">
  <script src="https://cdn.shopify.com/s/files/1/0001/0001/theme.js"></script>
  <script src="https://static.klaviyo.com/onsite/js/klaviyo.js"></script>
  <script>!function(f,b,e,v,n,t,s){fbq('init','123');}(window);</script>
</head>
<body>
  <h1>Welcome to Acme</h1>
  <p>We sell <b>premium</b> widgets.</p>
  <a href="https://www.linkedin.com/company/acme">LinkedIn</a>
  <a href="https://twitter.com/acme">Twitter</a>
  <script>var x=1;</script>
</body>
</html>
"""

WOO_HTML = """
<html lang="fr">
<head><title>Beta SARL</title>
<meta name="description" content="Beta vend des trucs.">
<link rel="stylesheet" href="/wp-content/plugins/woocommerce/assets/css/woocommerce.css">
<script src="https://js.hs-scripts.com/123.js"></script>
<script src="https://config.gorgias.chat/widget.js"></script>
</head><body>Beta site</body></html>
"""

EMPTY_HTML = "<html><head><title>Nothing here</title></head><body></body></html>"


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    # Pure extraction unit checks
    print("\n[extract_meta]")
    meta = extract_meta(SHOPIFY_HTML)
    assertion(meta["title"] == "Acme Co — Premium gear", f"title -> {meta['title']!r}", failures)
    assertion(meta["description"] == "Acme sells premium widgets.", "description ok", failures)
    assertion(meta["og_title"] == "Acme Co", "og:title ok", failures)
    assertion(meta["og_image"] == "https://acme.com/og.png", "og:image ok", failures)
    assertion(meta["canonical"] == "https://acme.com/", "canonical ok", failures)
    assertion(meta["language"] == "en", "lang ok", failures)
    assertion(any("linkedin.com" in s for s in meta["social_links"]), "linkedin link captured", failures)
    assertion(any("twitter.com" in s for s in meta["social_links"]), "twitter link captured", failures)

    print("\n[detect_tech_stack]")
    tech, ecom = detect_tech_stack(SHOPIFY_HTML)
    assertion("Shopify" in tech, f"Shopify detected -> {tech}", failures)
    assertion("Klaviyo" in tech, "Klaviyo detected", failures)
    assertion("Meta Pixel" in tech, "Meta Pixel detected", failures)
    assertion(ecom == "shopify", f"ecommerce_platform=shopify -> {ecom}", failures)
    tech2, ecom2 = detect_tech_stack(WOO_HTML)
    assertion("WooCommerce" in tech2, "WooCommerce detected", failures)
    assertion("HubSpot" in tech2, "HubSpot detected", failures)
    assertion("Gorgias" in tech2, "Gorgias detected", failures)
    assertion(ecom2 == "woocommerce", "ecommerce_platform=woocommerce", failures)
    tech3, ecom3 = detect_tech_stack(EMPTY_HTML)
    assertion(tech3 == [] and ecom3 is None, "empty html -> no tech", failures)

    print("\n[extract_visible_text]")
    text = extract_visible_text(SHOPIFY_HTML)
    assertion("Welcome to Acme" in text, "headline in text", failures)
    assertion("var x=1" not in text, "script content stripped", failures)

    print("\n[build_snapshot_from_fetch]")
    snap = build_snapshot_from_fetch(FetchResult(url="https://acme.com", status_code=200, html=SHOPIFY_HTML))
    assertion(snap["ok"] is True, "snapshot.ok=True", failures)
    assertion(snap["ecommerce_platform"] == "shopify", "snapshot.ecom=shopify", failures)
    assertion("Klaviyo" in snap["tech_stack"], "snapshot.tech_stack contains Klaviyo", failures)

    # Inject fake fetcher for service-level test
    fake = FakeFetcher({
        "acme.com": SHOPIFY_HTML,
        "beta.io": WOO_HTML,
        "broken.io": FetchResult(url="https://broken.io", status_code=500, html="", error="boom"),
    })
    set_default_fetcher(fake)

    # Build project + ICP + companies (no contacts needed)
    project_id = repos.projects.create({"name": "smoke09"})
    icp_id = repos.icps.create({
        "project_id": project_id, "name": "smoke",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })

    cid_acme = repos.companies.upsert_by_domain({"name": "Acme", "domain": "acme.com"})
    cid_beta = repos.companies.upsert_by_domain({"name": "Beta", "domain": "beta.io"})
    cid_brk = repos.companies.upsert_by_domain({"name": "Broken", "domain": "broken.io"})
    cid_nodom = repos.companies.create({"name": "NoDomain"})

    for cid in (cid_acme, cid_beta, cid_brk):
        repos.lead_candidates.upsert(
            icp_id=icp_id, company_id=cid, contact_id=None,
            data={"project_id": project_id},
        )

    print("\n[enrich_company single - acme]")
    res = enrich_company(repos, company_id=cid_acme)
    assertion(res["ok"] is True, "acme ok", failures)
    assertion(res["snapshot"]["ecommerce_platform"] == "shopify", "acme ecom=shopify", failures)
    assertion(res.get("enrichment_id"), "enrichment_id created", failures)
    co = repos.companies.get(cid_acme)
    assertion(co["ecommerce_platform"] == "shopify", "company.ecommerce_platform updated", failures)
    assertion(co["status"] == "enriched", "company.status -> enriched", failures)
    assertion("Klaviyo" in (co["tech_stack"] or []), "company.tech_stack merged", failures)
    assertion("premium widgets" in (co.get("description") or "").lower(), "company.description set", failures)

    print("\n[enrich_company - missing domain -> skipped]")
    res2 = enrich_company(repos, company_id=cid_nodom)
    assertion(res2.get("skipped") is True and res2.get("error") == "company_missing_domain",
              "missing domain skipped cleanly", failures)

    print("\n[enrich_company - fetch error -> ok=False, snapshot persisted]")
    res3 = enrich_company(repos, company_id=cid_brk)
    assertion(res3["ok"] is False, "broken.io ok=False", failures)
    assertion(res3.get("enrichment_id"), "enrichment row still persisted on failure", failures)

    print("\n[enrich_companies_batch - project scope, only_missing=True]")
    batch = enrich_companies_batch(
        repos, project_id=project_id, limit=10, only_missing=True,
    )
    # acme + broken.io already have rows -> only beta should run
    assertion(batch["scanned"] == 3, f"scanned 3 leads -> {batch['scanned']}", failures)
    assertion(batch["enriched"] == 1, f"only beta enriched -> {batch['enriched']}", failures)
    assertion(batch["skipped"] == 2, f"acme+broken skipped -> {batch['skipped']}", failures)
    co_beta = repos.companies.get(cid_beta)
    assertion(co_beta["ecommerce_platform"] == "woocommerce", "beta ecom=woocommerce", failures)

    print("\n[dry_run on already-enriched -> no new row]")
    rows_before = repos.company_enrichment.count({"company_id": cid_acme})
    dry = enrich_company(repos, company_id=cid_acme, dry_run=True)
    rows_after = repos.company_enrichment.count({"company_id": cid_acme})
    assertion(dry["ok"] is True and rows_after == rows_before, "dry run did not write", failures)

    print("\n[pipeline integration via run_type=company_enrichment]")
    # Add a fresh company without enrichment to force work
    cid_gamma = repos.companies.upsert_by_domain({"name": "Gamma", "domain": "gamma.dev"})
    fake.add("gamma.dev", "<html><head><title>Gamma</title>"
                          "<meta name='description' content='gamma desc'>"
                          "<script src='https://cdn.shopify.com/x.js'></script></head><body>g</body></html>")
    repos.lead_candidates.upsert(
        icp_id=icp_id, company_id=cid_gamma, contact_id=None,
        data={"project_id": project_id},
    )
    run_id = pipeline_runner.run_now(
        project_id=project_id,
        run_type="company_enrichment",
        icp_id=icp_id,
        config={"only_missing": True, "limit": 10},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") or detail
    assertion(run.get("status") == "completed", f"run completed -> {run.get('status')}", failures)
    co_gamma = repos.companies.get(cid_gamma)
    assertion(co_gamma["ecommerce_platform"] == "shopify", "gamma enriched via pipeline", failures)

    print("\n========")
    print("FAIL" if failures else "PASS", "—", len(failures), "failures")
    for f in failures:
        print(" -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
