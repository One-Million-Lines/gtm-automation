"""Experiment service (File 18).

create_experiment / assign_lead_to_experiment / score_experiment / declare_winner.
Wilson lower-bound test on positive_reply_rate.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from repositories.registry import RepoRegistry
from services.variant_allocator import (
    VariantAllocator, allocate_variant,
)
from vtutils.misc import now_iso


# ----------------------------------------------------------------------------
# Wilson lower bound (one-sided proportion CI). z=1.96 for 95% CL.
# ----------------------------------------------------------------------------

def wilson_lower_bound(positives: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    phat = float(positives) / float(n)
    denom = 1.0 + (z * z) / n
    centre = phat + (z * z) / (2.0 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + (z * z) / (4.0 * n)) / n)
    return max(0.0, (centre - margin) / denom)


# ----------------------------------------------------------------------------
# create_experiment
# ----------------------------------------------------------------------------

def create_experiment(
    repos: RepoRegistry,
    *,
    project_id: int,
    icp_id: Optional[int],
    name: str,
    variants: list[dict],
    hypothesis: Optional[str] = None,
    allocation: str = "hash",
    primary_metric: str = "positive_reply_rate",
    min_sample_size: int = 30,
    confidence_level: float = 0.95,
    config: Optional[dict] = None,
    status: str = "draft",
) -> dict:
    if not name or not str(name).strip():
        raise ValueError("name required")
    if not variants:
        raise ValueError("at least one variant required")

    exp_id = repos.outreach_experiments.create({
        "project_id": int(project_id),
        "icp_id": int(icp_id) if icp_id is not None else None,
        "name": str(name).strip(),
        "hypothesis": hypothesis,
        "status": status,
        "allocation": allocation,
        "primary_metric": primary_metric,
        "min_sample_size": int(min_sample_size),
        "confidence_level": float(confidence_level),
        "config": config or {},
    })

    has_control = any(bool(v.get("is_control")) for v in variants)
    created_variants: list[dict] = []
    for idx, v in enumerate(variants):
        is_control = bool(v.get("is_control"))
        if not has_control and idx == 0:
            is_control = True
        vid = repos.outreach_variants.create({
            "experiment_id": exp_id,
            "name": str(v.get("name") or f"variant_{idx + 1}").strip(),
            "weight": float(v.get("weight") or 1.0),
            "subject_template": v.get("subject_template"),
            "body_template": v.get("body_template"),
            "cta_template": v.get("cta_template"),
            "params": v.get("params") or {},
            "is_control": 1 if is_control else 0,
        })
        created_variants.append(repos.outreach_variants.get(vid))

    exp = repos.outreach_experiments.get(exp_id)
    exp["variants"] = created_variants
    return exp


# ----------------------------------------------------------------------------
# assign_lead_to_experiment
# ----------------------------------------------------------------------------

def assign_lead_to_experiment(
    repos: RepoRegistry,
    lead_id: int,
    experiment_id: int,
    *,
    allocator: VariantAllocator | None = None,
) -> dict:
    existing = repos.lead_variant_assignments.get_for_lead(lead_id, experiment_id)
    if existing:
        return existing

    exp = repos.outreach_experiments.get(int(experiment_id))
    if not exp:
        raise ValueError(f"experiment {experiment_id} not found")
    variants = repos.outreach_variants.list_for_experiment(int(experiment_id))
    if not variants:
        raise ValueError(f"experiment {experiment_id} has no variants")
    chosen = allocate_variant(exp, variants, int(lead_id), allocator=allocator)
    aid, _ = repos.lead_variant_assignments.assign_lead(
        int(lead_id), int(experiment_id), int(chosen["id"]),
    )
    return repos.lead_variant_assignments.get(aid)


def find_active_experiment_for_lead(
    repos: RepoRegistry, lead: dict,
) -> Optional[dict]:
    """Find a 'running' experiment that matches the lead's project + icp."""
    pid = lead.get("project_id")
    if not pid:
        return None
    rows = repos.outreach_experiments.list_for_project(int(pid), status="running")
    if not rows:
        return None
    icp_id = lead.get("icp_id")
    # Prefer exact icp match, then experiments with no icp scope
    for r in rows:
        if r.get("icp_id") and icp_id and int(r["icp_id"]) == int(icp_id):
            return r
    for r in rows:
        if not r.get("icp_id"):
            return r
    return None


# ----------------------------------------------------------------------------
# Variant-level send/reply stats
# ----------------------------------------------------------------------------

def _variant_send_stats(repos: RepoRegistry, experiment_id: int) -> dict[int, dict]:
    """Per variant_id: {sent, replied, positive}."""
    storage = repos.outreach_variants.storage
    sql = (
        "SELECT om.variant_id AS variant_id, "
        "  SUM(CASE WHEN os.status IN ('sent','opened','replied') THEN 1 ELSE 0 END) AS sent, "
        "  SUM(CASE WHEN os.status='replied' THEN 1 ELSE 0 END) AS replied "
        "FROM outreach_messages om "
        "INNER JOIN outreach_sends os ON os.outreach_message_id = om.id "
        "INNER JOIN outreach_variants ov ON ov.id = om.variant_id "
        "WHERE ov.experiment_id = ? "
        "GROUP BY om.variant_id"
    )
    rows = storage.fetchall(sql, (int(experiment_id),))
    stats: dict[int, dict] = {}
    for r in rows:
        vid = r.get("variant_id")
        if vid is None:
            continue
        stats[int(vid)] = {
            "sent": int(r["sent"] or 0),
            "replied": int(r["replied"] or 0),
            "positive": 0,
        }

    sql_pos = (
        "SELECT om.variant_id AS variant_id, COUNT(*) AS n "
        "FROM outreach_replies orep "
        "INNER JOIN outreach_messages om ON om.id = orep.outreach_message_id "
        "INNER JOIN outreach_variants ov ON ov.id = om.variant_id "
        "WHERE ov.experiment_id = ? AND orep.intent='positive' "
        "GROUP BY om.variant_id"
    )
    pos_rows = storage.fetchall(sql_pos, (int(experiment_id),))
    for r in pos_rows:
        vid = r.get("variant_id")
        if vid is None:
            continue
        stats.setdefault(int(vid), {"sent": 0, "replied": 0, "positive": 0})
        stats[int(vid)]["positive"] = int(r["n"] or 0)
    return stats


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def score_experiment(
    repos: RepoRegistry,
    experiment_id: int,
    *,
    z: float = 1.96,
) -> dict:
    exp = repos.outreach_experiments.get(int(experiment_id))
    if not exp:
        raise ValueError(f"experiment {experiment_id} not found")
    variants = repos.outreach_variants.list_for_experiment(int(experiment_id))
    stats = _variant_send_stats(repos, int(experiment_id))

    control = next((v for v in variants if int(v.get("is_control") or 0) == 1), None)
    control_id = int(control["id"]) if control else None
    control_pos_rate = (
        _rate(stats.get(control_id, {}).get("positive", 0),
              stats.get(control_id, {}).get("sent", 0))
        if control_id is not None else 0.0
    )

    by_variant: list[dict] = []
    min_n = int(exp.get("min_sample_size") or 30)
    for v in variants:
        vid = int(v["id"])
        s = stats.get(vid, {"sent": 0, "replied": 0, "positive": 0})
        sent = int(s["sent"])
        replied = int(s["replied"])
        positive = int(s["positive"])
        pos_rate = _rate(positive, sent)
        reply_rate = _rate(replied, sent)
        wlow = round(wilson_lower_bound(positive, sent, z=z), 4)
        lift = (
            round((pos_rate - control_pos_rate) / control_pos_rate, 4)
            if control_pos_rate > 0 else None
        )
        by_variant.append({
            "variant_id": vid,
            "name": v.get("name"),
            "is_control": bool(v.get("is_control")),
            "sent": sent,
            "replied": replied,
            "positive": positive,
            "reply_rate": reply_rate,
            "positive_reply_rate": pos_rate,
            "lift_vs_control": lift,
            "wilson_lower": wlow,
        })

    # Leader = max wilson_lower among non-empty
    candidates = [v for v in by_variant if v["sent"] >= 1]
    leader = max(candidates, key=lambda v: v["wilson_lower"], default=None)
    leader_id = leader["variant_id"] if leader else None

    # Ready to declare: leader has min_sample_size sent AND its wilson_lower
    # exceeds control's positive_reply_rate AND it's not the control.
    ready = False
    if leader and control_id is not None and int(leader["variant_id"]) != control_id:
        if leader["sent"] >= min_n and leader["wilson_lower"] > control_pos_rate:
            ready = True
    elif leader and control_id is None:
        # No control? Just require min sample
        ready = leader["sent"] >= min_n

    return {
        "experiment_id": int(experiment_id),
        "status": exp.get("status"),
        "primary_metric": exp.get("primary_metric"),
        "min_sample_size": min_n,
        "confidence_level": exp.get("confidence_level"),
        "control_variant_id": control_id,
        "by_variant": by_variant,
        "leader_variant_id": leader_id,
        "winner_variant_id": exp.get("winner_variant_id"),
        "ready_to_declare": ready,
        "computed_at": now_iso(),
    }


# ----------------------------------------------------------------------------
# declare_winner
# ----------------------------------------------------------------------------

def declare_winner(
    repos: RepoRegistry, experiment_id: int, variant_id: int,
) -> dict:
    exp = repos.outreach_experiments.get(int(experiment_id))
    if not exp:
        raise ValueError(f"experiment {experiment_id} not found")
    v = repos.outreach_variants.get(int(variant_id))
    if not v or int(v.get("experiment_id") or 0) != int(experiment_id):
        raise ValueError(f"variant {variant_id} not in experiment {experiment_id}")
    repos.outreach_experiments.set_winner(int(experiment_id), int(variant_id))
    return repos.outreach_experiments.get(int(experiment_id))


# ----------------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------------

def start_experiment(repos: RepoRegistry, experiment_id: int) -> dict:
    exp = repos.outreach_experiments.get(int(experiment_id))
    if not exp:
        raise ValueError("experiment not found")
    repos.outreach_experiments.set_status(
        int(experiment_id), "running", started_at=now_iso(),
    )
    return repos.outreach_experiments.get(int(experiment_id))


def pause_experiment(repos: RepoRegistry, experiment_id: int) -> dict:
    exp = repos.outreach_experiments.get(int(experiment_id))
    if not exp:
        raise ValueError("experiment not found")
    repos.outreach_experiments.set_status(int(experiment_id), "paused")
    return repos.outreach_experiments.get(int(experiment_id))


# ----------------------------------------------------------------------------
# Template rendering
# ----------------------------------------------------------------------------

class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + str(key) + "}"


def render_variant(variant: dict, ctx: dict) -> dict:
    """Render subject/body/cta templates with str.format_map(safe_dict)."""
    safe = _SafeDict(ctx)

    def _r(t: Any) -> Any:
        if not t or not isinstance(t, str):
            return t
        try:
            return t.format_map(safe)
        except Exception:
            return t

    return {
        "subject": _r(variant.get("subject_template")),
        "body": _r(variant.get("body_template")),
        "cta": _r(variant.get("cta_template")),
    }
