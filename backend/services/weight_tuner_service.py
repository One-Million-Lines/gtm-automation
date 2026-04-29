"""Scoring weight tuner service (File 21).

Consumes File 20's `feedback_events` (applied=1) and proposes per-feature
weight deltas for an ICP's lead-scoring config. Versioned via
`scoring_weight_revisions`; revisions are *proposed* by default and require
explicit human approval (or auto-promote above a confidence threshold)
before they become *active*.

Pluggable `WeightTunerAdapter` (default `HeuristicWeightTuner`).
"""
from __future__ import annotations

import datetime as _dt
import math
from typing import Any, Iterable, Optional, Protocol

from services.lead_scorer import FIT_WEIGHTS, SIGNAL_WEIGHTS

REVISION_SOURCES = ("manual", "auto_tune", "rollback")
REVISION_STATUSES = ("proposed", "active", "archived", "rejected")

# Maps feedback kinds to a polarity in [-1, +1] used by the heuristic tuner.
KIND_POLARITY: dict[str, float] = {
    "thumbs_up":         +0.5,
    "thumbs_down":       -0.5,
    "lead_qualified":    +0.8,
    "lead_disqualified": -0.8,
    "meeting_booked":    +1.0,
    "won":               +1.0,
    "lost":              -0.6,
    "unsubscribe":       -1.0,
    "note":               0.0,
}

POSITIVE_KINDS = {k for k, p in KIND_POLARITY.items() if p > 0}
NEGATIVE_KINDS = {k for k, p in KIND_POLARITY.items() if p < 0}

# Heuristic tuner step size and clamps.
DEFAULT_LEARNING_RATE = 0.1
MIN_WEIGHT = 0.05
MAX_WEIGHT = 2.0


# ---------------------------------------------------------------------------
# Pluggable WeightTunerAdapter
# ---------------------------------------------------------------------------
class WeightTunerAdapter(Protocol):
    name: str

    def tune(
        self,
        *,
        baseline: dict[str, dict[str, float]],
        events: list[dict],
    ) -> dict[str, Any]:
        """Return {proposed_weights, stats, contributing_event_ids}."""
        ...


class HeuristicWeightTuner:
    """Simple per-feature win/loss heuristic.

    For each feedback event:
      - look up its KIND_POLARITY (skip 0.0).
      - apply a uniform per-feature nudge proportional to event.weight * polarity * lr.
      - positive feedback raises every signal weight slightly; negative lowers.
      - fit weights are nudged uniformly too, then renormalised to sum=1.0.

    This is intentionally tiny — leaves room for an LLM/gradient tuner later.
    """

    name = "heuristic_v1"

    def __init__(self, learning_rate: float = DEFAULT_LEARNING_RATE) -> None:
        self.learning_rate = float(learning_rate)

    def tune(
        self,
        *,
        baseline: dict[str, dict[str, float]],
        events: list[dict],
    ) -> dict[str, Any]:
        fit_in = dict(baseline.get("fit") or {})
        sig_in = dict(baseline.get("signal") or {})

        polarities: list[float] = []
        positive_n = 0
        negative_n = 0
        contributing: list[int] = []
        per_feature_shift: dict[str, float] = {}

        for ev in events:
            kind = ev.get("kind")
            pol = KIND_POLARITY.get(kind, 0.0)
            if pol == 0.0:
                continue
            w = float(ev.get("weight") or 1.0)
            polarities.append(pol * w)
            contributing.append(int(ev.get("id")))
            if pol > 0:
                positive_n += 1
            else:
                negative_n += 1

        # Total signed nudge across the dataset.
        total_signal = sum(polarities)
        dataset_size = len(polarities)

        # Multiplicative nudge per signal feature; clamped.
        sig_out: dict[str, float] = {}
        for k, v in sig_in.items():
            nudge = self.learning_rate * total_signal / max(1, dataset_size)
            new_v = float(v) * (1.0 + nudge)
            new_v = max(MIN_WEIGHT, min(MAX_WEIGHT, new_v))
            sig_out[k] = round(new_v, 4)
            per_feature_shift[f"signal.{k}"] = round(new_v - float(v), 4)

        # Multiplicative nudge per fit feature, then renormalise to sum=1.0.
        fit_raw: dict[str, float] = {}
        for k, v in fit_in.items():
            nudge = self.learning_rate * total_signal / max(1, dataset_size)
            new_v = float(v) * (1.0 + nudge)
            new_v = max(MIN_WEIGHT, new_v)
            fit_raw[k] = new_v
        s = sum(fit_raw.values()) or 1.0
        fit_out = {k: round(v / s, 4) for k, v in fit_raw.items()}
        for k, new_v in fit_out.items():
            per_feature_shift[f"fit.{k}"] = round(new_v - float(fit_in.get(k, 0.0)), 4)

        shifts = list(per_feature_shift.values())
        mean_shift = round(sum(abs(s) for s in shifts) / max(1, len(shifts)), 5)
        max_shift = round(max((abs(s) for s in shifts), default=0.0), 5)

        # Confidence: scaled by dataset size (saturates at ~30 events) +
        # purity (|positive - negative| / dataset_size).
        if dataset_size <= 0:
            confidence = 0.0
        else:
            size_factor = 1.0 - math.exp(-dataset_size / 15.0)
            purity = abs(positive_n - negative_n) / dataset_size
            confidence = round(min(1.0, size_factor * (0.5 + 0.5 * purity)), 4)

        return {
            "proposed_weights": {"fit": fit_out, "signal": sig_out},
            "contributing_event_ids": contributing,
            "stats": {
                "tuner": self.name,
                "dataset_size": dataset_size,
                "positive_n": positive_n,
                "negative_n": negative_n,
                "mean_weight_shift": mean_shift,
                "max_shift": max_shift,
                "per_feature_shift": per_feature_shift,
                "confidence": confidence,
                "learning_rate": self.learning_rate,
            },
        }


# ---------------------------------------------------------------------------
# Pluggable default adapter
# ---------------------------------------------------------------------------
_default_weight_tuner: Optional[WeightTunerAdapter] = HeuristicWeightTuner()


def get_default_weight_tuner() -> WeightTunerAdapter:
    global _default_weight_tuner
    if _default_weight_tuner is None:
        _default_weight_tuner = HeuristicWeightTuner()
    return _default_weight_tuner


def set_default_weight_tuner(adapter: WeightTunerAdapter | None) -> None:
    global _default_weight_tuner
    _default_weight_tuner = adapter if adapter is not None else HeuristicWeightTuner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _module_baseline_weights() -> dict[str, dict[str, float]]:
    return {"fit": dict(FIT_WEIGHTS), "signal": dict(SIGNAL_WEIGHTS)}


def baseline_weights_for_icp(repos, icp_id: int) -> dict[str, dict[str, float]]:
    """Active revision wins; otherwise fall back to module defaults."""
    active = repos.scoring_weight_revisions.get_active_for_icp(int(icp_id))
    if active and isinstance(active.get("proposed_weights"), dict):
        pw = active["proposed_weights"]
        return {
            "fit": dict(pw.get("fit") or {}),
            "signal": dict(pw.get("signal") or {}),
        }
    return _module_baseline_weights()


def diff_weights(
    baseline: dict[str, dict[str, float]],
    proposed: dict[str, dict[str, float]],
) -> list[dict]:
    rows: list[dict] = []
    for ns in ("fit", "signal"):
        b = baseline.get(ns) or {}
        p = proposed.get(ns) or {}
        keys = sorted(set(b.keys()) | set(p.keys()))
        for k in keys:
            bv = float(b.get(k, 0.0))
            pv = float(p.get(k, 0.0))
            rows.append({
                "namespace": ns,
                "key": k,
                "baseline": round(bv, 4),
                "proposed": round(pv, 4),
                "delta": round(pv - bv, 4),
            })
    return rows


def _collect_applied_events(
    repos, *, project_id: int, icp_id: int, limit: int = 1000,
) -> list[dict]:
    """Pull applied feedback events for this project; filter to icp_id when set on event,
    otherwise include events whose lead belongs to this icp."""
    rows = repos.feedback_events.list_for_project(
        int(project_id), applied=1, limit=int(limit),
    )
    out: list[dict] = []
    for ev in rows:
        ev_icp = ev.get("icp_id")
        if ev_icp == icp_id:
            out.append(ev)
            continue
        if ev_icp is None and ev.get("lead_id"):
            lead = repos.lead_candidates.get(int(ev["lead_id"]))
            if lead and int(lead.get("icp_id") or 0) == int(icp_id):
                out.append(ev)
    return out


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------
def propose_revision(
    repos,
    *,
    icp_id: int,
    project_id: int,
    notes: str | None = None,
    created_by: str | None = None,
    tuner: WeightTunerAdapter | None = None,
    event_limit: int = 1000,
) -> dict[str, Any]:
    """Compute a proposed weight revision. Does not change the active one."""
    icp = repos.icps.get(int(icp_id))
    if not icp:
        raise ValueError(f"icp not found: {icp_id}")
    project = repos.projects.get(int(project_id))
    if not project:
        raise ValueError(f"project not found: {project_id}")

    tuner = tuner or get_default_weight_tuner()
    baseline = baseline_weights_for_icp(repos, icp_id)
    events = _collect_applied_events(
        repos, project_id=project_id, icp_id=icp_id, limit=event_limit,
    )
    result = tuner.tune(baseline=baseline, events=events)

    active = repos.scoring_weight_revisions.get_active_for_icp(icp_id)
    rev_id = repos.scoring_weight_revisions.create({
        "icp_id": int(icp_id),
        "project_id": int(project_id),
        "parent_revision_id": (active or {}).get("id"),
        "source": "auto_tune",
        "status": "proposed",
        "proposed_weights": result["proposed_weights"],
        "baseline_weights": baseline,
        "contributing_event_ids": result["contributing_event_ids"],
        "stats": result["stats"],
        "notes": notes,
        "created_by": created_by or "auto_tune",
    })
    revision = repos.scoring_weight_revisions.get(rev_id)
    return {
        "revision": revision,
        "baseline": baseline,
        "proposed": result["proposed_weights"],
        "stats": result["stats"],
        "contributing_event_ids": result["contributing_event_ids"],
        "diff": diff_weights(baseline, result["proposed_weights"]),
    }


def approve_revision(repos, revision_id: int) -> dict[str, Any]:
    rev = repos.scoring_weight_revisions.get(int(revision_id))
    if not rev:
        raise ValueError(f"revision not found: {revision_id}")
    if rev["status"] not in ("proposed", "archived"):
        raise ValueError(f"cannot approve revision in status {rev['status']!r}")

    icp_id = int(rev["icp_id"])
    now = _now_iso()
    active = repos.scoring_weight_revisions.get_active_for_icp(icp_id)
    if active and active["id"] != rev["id"]:
        repos.scoring_weight_revisions.update(active["id"], {
            "status": "archived", "archived_at": now,
        })
    repos.scoring_weight_revisions.update(rev["id"], {
        "status": "active", "activated_at": now, "archived_at": None,
    })
    return {
        "revision": repos.scoring_weight_revisions.get(rev["id"]),
        "previous_active_id": (active or {}).get("id"),
    }


def reject_revision(repos, revision_id: int, *, reason: str | None = None) -> dict[str, Any]:
    rev = repos.scoring_weight_revisions.get(int(revision_id))
    if not rev:
        raise ValueError(f"revision not found: {revision_id}")
    if rev["status"] != "proposed":
        raise ValueError(f"cannot reject revision in status {rev['status']!r}")
    update: dict[str, Any] = {"status": "rejected"}
    if reason:
        existing = rev.get("notes") or ""
        update["notes"] = (existing + ("\n" if existing else "") + f"rejected: {reason}").strip()
    repos.scoring_weight_revisions.update(rev["id"], update)
    return {"revision": repos.scoring_weight_revisions.get(rev["id"])}


def rollback_to(
    repos,
    revision_id: int,
    *,
    created_by: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Clone the target revision into a new active row (status='rollback')."""
    target = repos.scoring_weight_revisions.get(int(revision_id))
    if not target:
        raise ValueError(f"revision not found: {revision_id}")

    icp_id = int(target["icp_id"])
    now = _now_iso()
    active = repos.scoring_weight_revisions.get_active_for_icp(icp_id)
    if active and active["id"] != target["id"]:
        repos.scoring_weight_revisions.update(active["id"], {
            "status": "archived", "archived_at": now,
        })
    new_id = repos.scoring_weight_revisions.create({
        "icp_id": icp_id,
        "project_id": int(target["project_id"]),
        "parent_revision_id": int(target["id"]),
        "source": "rollback",
        "status": "active",
        "proposed_weights": target.get("proposed_weights"),
        "baseline_weights": target.get("baseline_weights"),
        "contributing_event_ids": target.get("contributing_event_ids") or [],
        "stats": {
            "rolled_back_from": int(target["id"]),
            "previous_active_id": (active or {}).get("id"),
        },
        "notes": notes or f"rollback to revision {target['id']}",
        "created_by": created_by or "rollback",
        "activated_at": now,
    })
    return {
        "revision": repos.scoring_weight_revisions.get(new_id),
        "previous_active_id": (active or {}).get("id"),
        "source_revision_id": int(target["id"]),
    }


def revision_summary(repos, icp_id: int) -> dict[str, Any]:
    icp = repos.icps.get(int(icp_id))
    if not icp:
        raise ValueError(f"icp not found: {icp_id}")
    active = repos.scoring_weight_revisions.get_active_for_icp(int(icp_id))
    proposed = repos.scoring_weight_revisions.list_proposed_for_icp(int(icp_id))
    history = repos.scoring_weight_revisions.list_for_icp(int(icp_id), limit=200)
    baseline = baseline_weights_for_icp(repos, int(icp_id))
    return {
        "icp_id": int(icp_id),
        "active": active,
        "active_weights": baseline,
        "module_defaults": _module_baseline_weights(),
        "proposed": proposed,
        "history": history,
    }


def run_tuning_for_project(
    repos,
    *,
    project_id: int,
    icp_ids: Iterable[int] | None = None,
    auto_promote: bool = False,
    confidence_threshold: float = 0.7,
    notes: str | None = None,
    created_by: str | None = None,
    tuner: WeightTunerAdapter | None = None,
) -> dict[str, Any]:
    project = repos.projects.get(int(project_id))
    if not project:
        raise ValueError(f"project not found: {project_id}")

    if icp_ids is None:
        icps = repos.icps.find({"project_id": int(project_id)})
        ids = [int(i["id"]) for i in icps]
    else:
        ids = [int(i) for i in icp_ids]

    proposed_revisions: list[dict] = []
    promoted: list[dict] = []
    skipped: list[dict] = []

    for icp_id in ids:
        proposal = propose_revision(
            repos, icp_id=icp_id, project_id=int(project_id),
            notes=notes, created_by=created_by, tuner=tuner,
        )
        proposed_revisions.append(proposal["revision"])
        confidence = float((proposal["stats"] or {}).get("confidence") or 0.0)
        if auto_promote and confidence >= float(confidence_threshold):
            promoted.append(approve_revision(
                repos, int(proposal["revision"]["id"]),
            )["revision"])
        else:
            skipped.append({
                "icp_id": icp_id,
                "revision_id": int(proposal["revision"]["id"]),
                "confidence": confidence,
            })

    return {
        "project_id": int(project_id),
        "icp_ids": ids,
        "proposed_count": len(proposed_revisions),
        "promoted_count": len(promoted),
        "skipped_count": len(skipped),
        "proposed": proposed_revisions,
        "promoted": promoted,
        "skipped": skipped,
        "auto_promote": bool(auto_promote),
        "confidence_threshold": float(confidence_threshold),
    }
