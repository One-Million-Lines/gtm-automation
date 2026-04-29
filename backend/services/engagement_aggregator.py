"""EngagementAggregator service (File 17).

Computes per-campaign (== per-project, optionally per-icp) funnel metrics
from outreach_sends + outreach_replies + lead_candidates.

Pluggable default pattern (mirrors File 15/16):
    _default_aggregator
    set_default_engagement_aggregator(None resets)
    get_default_engagement_aggregator()
    compute_engagement(repos, ...)  convenience
"""
from __future__ import annotations

from typing import Any, Protocol

from repositories.registry import RepoRegistry
from vtutils.misc import now_iso


# ============================================================================
# Protocol
# ============================================================================
class EngagementAggregator(Protocol):
    name: str

    def compute(
        self,
        project_id: int,
        *,
        icp_id: int | None = None,
        window_days: int = 30,
        use_cache: bool = True,
    ) -> dict: ...


# ============================================================================
# SQL implementation
# ============================================================================
class SqlEngagementAggregator:
    name = "sql"

    def __init__(self, repos: RepoRegistry) -> None:
        self.repos = repos

    # ------------------------------------------------------------------
    def compute(
        self,
        project_id: int,
        *,
        icp_id: int | None = None,
        window_days: int = 30,
        use_cache: bool = True,
    ) -> dict:
        if use_cache:
            cached = self.repos.engagement_snapshots.latest_for(
                project_id, icp_id=icp_id, window_days=window_days,
            )
            if cached and cached.get("payload"):
                payload = dict(cached["payload"])
                payload["from_cache"] = True
                return payload

        payload = self._compute_fresh(project_id, icp_id=icp_id, window_days=window_days)
        self.repos.engagement_snapshots.upsert_for(
            project_id, icp_id, window_days, payload,
        )
        payload["from_cache"] = False
        return payload

    # ------------------------------------------------------------------
    def _compute_fresh(self, project_id: int, *, icp_id: int | None,
                       window_days: int) -> dict:
        storage = self.repos.engagement_snapshots.storage

        # ---- common WHERE for sends scoped to project (+icp) ----
        send_where = ["lc.project_id = ?"]
        send_params: list[Any] = [int(project_id)]
        if icp_id is not None:
            send_where.append("lc.icp_id = ?")
            send_params.append(int(icp_id))
        send_where_sql = " AND ".join(send_where)

        # ---- send status counts ----
        sql_status = (
            "SELECT os.status AS status, COUNT(*) AS n "
            "FROM outreach_sends os "
            "INNER JOIN outreach_messages om ON om.id = os.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {send_where_sql} GROUP BY os.status"
        )
        status_rows = storage.fetchall(sql_status, tuple(send_params))
        by_status: dict[str, int] = {r["status"] or "unknown": int(r["n"]) for r in status_rows}

        sent_count = sum(
            v for k, v in by_status.items()
            if k in ("sent", "opened", "replied")
        )
        opened_count = by_status.get("opened", 0) + by_status.get("replied", 0)
        replied_count = by_status.get("replied", 0)
        bounced_count = by_status.get("bounced", 0)
        failed_count = by_status.get("failed", 0)

        # ---- sent today / 7d / 30d ----
        sql_sent_today = (
            "SELECT COUNT(*) AS n FROM outreach_sends os "
            "INNER JOIN outreach_messages om ON om.id = os.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {send_where_sql} "
            "AND os.status IN ('sent','opened','replied') "
            "AND date(COALESCE(os.sent_at, os.attempted_at)) = date('now')"
        )
        sent_today = int(storage.fetchall(sql_sent_today, tuple(send_params))[0]["n"])

        sql_sent_window = (
            "SELECT COUNT(*) AS n FROM outreach_sends os "
            "INNER JOIN outreach_messages om ON om.id = os.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {send_where_sql} "
            "AND os.status IN ('sent','opened','replied') "
            "AND date(COALESCE(os.sent_at, os.attempted_at)) >= date('now', ?)"
        )
        sent_7d = int(storage.fetchall(sql_sent_window, (*send_params, "-7 day"))[0]["n"])
        sent_30d = int(storage.fetchall(sql_sent_window, (*send_params, "-30 day"))[0]["n"])
        sent_window = int(
            storage.fetchall(sql_sent_window, (*send_params, f"-{int(window_days)} day"))[0]["n"]
        )

        # ---- daily series (window_days) ----
        sql_daily = (
            "SELECT date(COALESCE(os.sent_at, os.attempted_at)) AS d, "
            "  SUM(CASE WHEN os.status IN ('sent','opened','replied') THEN 1 ELSE 0 END) AS sent, "
            "  SUM(CASE WHEN os.status IN ('opened','replied') THEN 1 ELSE 0 END) AS opened, "
            "  SUM(CASE WHEN os.status='replied' THEN 1 ELSE 0 END) AS replied, "
            "  SUM(CASE WHEN os.status='bounced' THEN 1 ELSE 0 END) AS bounced "
            "FROM outreach_sends os "
            "INNER JOIN outreach_messages om ON om.id = os.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {send_where_sql} "
            "AND date(COALESCE(os.sent_at, os.attempted_at)) >= date('now', ?) "
            "GROUP BY d ORDER BY d"
        )
        daily_rows = storage.fetchall(
            sql_daily, (*send_params, f"-{int(window_days)} day"),
        )
        daily_series = [
            {
                "date": r["d"],
                "sent": int(r["sent"] or 0),
                "opened": int(r["opened"] or 0),
                "replied": int(r["replied"] or 0),
                "bounced": int(r["bounced"] or 0),
            }
            for r in daily_rows if r["d"]
        ]

        # ---- replies by intent ----
        sql_intent = (
            "SELECT orep.intent AS intent, COUNT(*) AS n "
            "FROM outreach_replies orep "
            "INNER JOIN outreach_messages om ON om.id = orep.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {send_where_sql} GROUP BY orep.intent"
        )
        intent_rows = storage.fetchall(sql_intent, tuple(send_params))
        by_intent: dict[str, int] = {
            (r["intent"] or "neutral"): int(r["n"]) for r in intent_rows
        }
        positive_replies = int(by_intent.get("positive", 0))
        unsubscribed_count = int(by_intent.get("unsubscribe", 0))

        # ---- top replied companies ----
        sql_top = (
            "SELECT co.id AS company_id, co.name AS company_name, COUNT(*) AS replies "
            "FROM outreach_replies orep "
            "INNER JOIN outreach_messages om ON om.id = orep.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            "LEFT JOIN companies co ON co.id = lc.company_id "
            f"WHERE {send_where_sql} "
            "GROUP BY co.id, co.name ORDER BY replies DESC, co.name LIMIT 10"
        )
        top_rows = storage.fetchall(sql_top, tuple(send_params))
        top_replied_companies = [
            {
                "company_id": r["company_id"],
                "company_name": r["company_name"],
                "replies": int(r["replies"]),
            }
            for r in top_rows if r["company_id"] is not None
        ]

        # ---- funnel ----
        funnel = self._compute_funnel(project_id, icp_id=icp_id)

        # ---- rates ----
        def _rate(num: int, den: int) -> float:
            return round(num / den, 4) if den else 0.0

        return {
            "project_id": int(project_id),
            "icp_id": int(icp_id) if icp_id is not None else None,
            "window_days": int(window_days),
            "computed_at": now_iso(),
            # send stats
            "sent_count": sent_count,
            "sent_today": sent_today,
            "sent_7d": sent_7d,
            "sent_30d": sent_30d,
            "sent_window": sent_window,
            # opens / replies
            "opened_count": opened_count,
            "opened_rate": _rate(opened_count, sent_count),
            "replied_count": replied_count,
            "reply_rate": _rate(replied_count, sent_count),
            "positive_reply_count": positive_replies,
            "positive_reply_rate": _rate(positive_replies, sent_count),
            # bounce / fail / unsub
            "bounced_count": bounced_count,
            "bounce_rate": _rate(bounced_count, sent_count + bounced_count + failed_count),
            "failed_count": failed_count,
            "unsubscribed_count": unsubscribed_count,
            "unsubscribe_rate": _rate(unsubscribed_count, sent_count),
            # detail
            "by_status": by_status,
            "by_intent": by_intent,
            "daily_series": daily_series,
            "top_replied_companies": top_replied_companies,
            "funnel": funnel,
        }

    # ------------------------------------------------------------------
    def _compute_funnel(self, project_id: int, *, icp_id: int | None) -> dict:
        storage = self.repos.engagement_snapshots.storage
        where = ["lc.project_id = ?"]
        params: list[Any] = [int(project_id)]
        if icp_id is not None:
            where.append("lc.icp_id = ?")
            params.append(int(icp_id))
        where_sql = " AND ".join(where)

        # discovered = distinct companies referenced by lead_candidates for project (+icp)
        sql_disc = (
            "SELECT COUNT(DISTINCT lc.company_id) AS n FROM lead_candidates lc "
            f"WHERE {where_sql} AND lc.company_id IS NOT NULL"
        )
        discovered = int(storage.fetchall(sql_disc, tuple(params))[0]["n"])

        # scored leads
        sql_scored = (
            f"SELECT COUNT(*) AS n FROM lead_candidates lc WHERE {where_sql} "
            "AND lc.lead_status IN ('scored','approved','sent','replied','qualified')"
        )
        scored = int(storage.fetchall(sql_scored, tuple(params))[0]["n"])

        # approved messages (joined to leads via project)
        sql_approved = (
            "SELECT COUNT(*) AS n FROM outreach_messages om "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {where_sql} AND om.status IN ('approved','sent')"
        )
        approved = int(storage.fetchall(sql_approved, tuple(params))[0]["n"])

        # sent / opened / replied / positive
        sql_sent = (
            "SELECT "
            "  SUM(CASE WHEN os.status IN ('sent','opened','replied') THEN 1 ELSE 0 END) AS sent, "
            "  SUM(CASE WHEN os.status IN ('opened','replied') THEN 1 ELSE 0 END) AS opened, "
            "  SUM(CASE WHEN os.status='replied' THEN 1 ELSE 0 END) AS replied "
            "FROM outreach_sends os "
            "INNER JOIN outreach_messages om ON om.id = os.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {where_sql}"
        )
        rs = storage.fetchall(sql_sent, tuple(params))
        sent = int((rs[0]["sent"] if rs else 0) or 0)
        opened = int((rs[0]["opened"] if rs else 0) or 0)
        replied = int((rs[0]["replied"] if rs else 0) or 0)

        sql_pos = (
            "SELECT COUNT(*) AS n FROM outreach_replies orep "
            "INNER JOIN outreach_messages om ON om.id = orep.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {where_sql} AND orep.intent='positive'"
        )
        positive = int(storage.fetchall(sql_pos, tuple(params))[0]["n"])

        return {
            "discovered": discovered,
            "scored": scored,
            "approved": approved,
            "sent": sent,
            "opened": opened,
            "replied": replied,
            "positive": positive,
        }


# ============================================================================
# Fake aggregator (tests)
# ============================================================================
class FakeEngagementAggregator:
    name = "fake"

    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {}

    def compute(self, project_id: int, *, icp_id: int | None = None,
                window_days: int = 30, use_cache: bool = True) -> dict:
        out = dict(self.payload)
        out.setdefault("project_id", int(project_id))
        out.setdefault("icp_id", int(icp_id) if icp_id is not None else None)
        out.setdefault("window_days", int(window_days))
        out.setdefault("from_cache", False)
        return out


# ============================================================================
# Pluggable default
# ============================================================================
_default_aggregator: EngagementAggregator | None = None


def set_default_engagement_aggregator(aggregator: EngagementAggregator | None) -> None:
    global _default_aggregator
    _default_aggregator = aggregator


def get_default_engagement_aggregator(repos: RepoRegistry | None = None) -> EngagementAggregator:
    global _default_aggregator
    if _default_aggregator is None:
        if repos is None:
            raise RuntimeError("no default engagement aggregator and no repos provided")
        _default_aggregator = SqlEngagementAggregator(repos)
    return _default_aggregator


def compute_engagement(
    repos: RepoRegistry,
    project_id: int,
    *,
    icp_id: int | None = None,
    window_days: int = 30,
    use_cache: bool = True,
    aggregator: EngagementAggregator | None = None,
) -> dict:
    agg = aggregator or get_default_engagement_aggregator(repos)
    return agg.compute(
        project_id, icp_id=icp_id, window_days=window_days, use_cache=use_cache,
    )
