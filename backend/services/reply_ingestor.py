"""Pluggable ReplyIngestor (File 16).

Implementations:
  - IMAPReplyIngestor:     aioimaplib polling UNSEEN; reads env IMAP_HOST/PORT/USER/PASS/FOLDER/USE_SSL
  - WebhookReplyIngestor:  parses provider webhook payloads (configurable field map)
  - FakeReplyIngestor:     deterministic for tests

A reply payload (returned by ingestors) is a dict:
    {
        "provider":            str,
        "message_id_external": str | None,
        "in_reply_to":         str | None,
        "from_email":          str | None,
        "from_name":           str | None,
        "subject":             str,
        "body":                str,
        "body_html":           str | None,
        "received_at":         iso str | None,
        "raw_response":        dict,
    }
"""
from __future__ import annotations

import asyncio
import os
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Protocol


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
class ReplyIngestor(Protocol):
    name: str

    def fetch(self, *, limit: int = 200) -> list[dict]:
        """Return a list of normalized reply payload dicts."""
        ...


def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# IMAP ingestor
# ---------------------------------------------------------------------------
@dataclass
class IMAPReplyIngestor:
    name: str = "imap"
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    folder: Optional[str] = None
    use_ssl: Optional[bool] = None

    def __post_init__(self) -> None:
        self.host = self.host or os.environ.get("IMAP_HOST")
        port_env = os.environ.get("IMAP_PORT")
        if self.port is None and port_env:
            self.port = int(port_env)
        self.username = self.username or os.environ.get("IMAP_USER")
        self.password = self.password or os.environ.get("IMAP_PASS")
        self.folder = self.folder or os.environ.get("IMAP_FOLDER", "INBOX")
        if self.use_ssl is None:
            self.use_ssl = os.environ.get("IMAP_USE_SSL", "true").lower() in ("1", "true", "yes")

    def fetch(self, *, limit: int = 200) -> list[dict]:
        if not self.host or not self.username or not self.password:
            return []
        try:
            import aioimaplib
            from email import message_from_bytes
            from email.utils import parseaddr, parsedate_to_datetime
        except Exception:  # pragma: no cover - dependency missing
            return []

        async def _run() -> list[dict]:
            cls = aioimaplib.IMAP4_SSL if self.use_ssl else aioimaplib.IMAP4
            client = cls(host=self.host, port=int(self.port or (993 if self.use_ssl else 143)))
            await client.wait_hello_from_server()
            await client.login(self.username, self.password)
            await client.select(self.folder or "INBOX")
            typ, data = await client.search("UNSEEN")
            ids = (data[0].decode().split() if data and data[0] else [])[:limit]
            out: list[dict] = []
            for uid in ids:
                typ, msg_data = await client.fetch(uid, "(RFC822)")
                if not msg_data:
                    continue
                raw_bytes = b""
                for part in msg_data:
                    if isinstance(part, (bytes, bytearray)) and part.startswith(b"From"):
                        raw_bytes = bytes(part)
                        break
                if not raw_bytes:
                    raw_bytes = b"".join(p for p in msg_data if isinstance(p, (bytes, bytearray)))
                msg = message_from_bytes(raw_bytes)
                from_name, from_email = parseaddr(msg.get("From", ""))
                received = msg.get("Date")
                try:
                    received_iso = parsedate_to_datetime(received).isoformat() if received else None
                except Exception:
                    received_iso = None
                body_text = ""
                body_html = None
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/plain" and not body_text:
                            try:
                                body_text = part.get_payload(decode=True).decode(errors="ignore")
                            except Exception:
                                body_text = part.get_payload() or ""
                        elif ct == "text/html" and not body_html:
                            try:
                                body_html = part.get_payload(decode=True).decode(errors="ignore")
                            except Exception:
                                body_html = part.get_payload()
                else:
                    try:
                        body_text = msg.get_payload(decode=True).decode(errors="ignore")
                    except Exception:
                        body_text = msg.get_payload() or ""
                out.append({
                    "provider": self.name,
                    "message_id_external": msg.get("Message-ID"),
                    "in_reply_to": msg.get("In-Reply-To") or msg.get("References"),
                    "from_email": from_email or None,
                    "from_name": from_name or None,
                    "subject": msg.get("Subject", ""),
                    "body": body_text,
                    "body_html": body_html,
                    "received_at": received_iso,
                    "raw_response": {"uid": uid, "headers": dict(msg.items())},
                })
            try:
                await client.logout()
            except Exception:
                pass
            return out

        try:
            return asyncio.run(_run())
        except Exception:  # pragma: no cover - defensive
            return []


# ---------------------------------------------------------------------------
# Webhook ingestor
# ---------------------------------------------------------------------------
@dataclass
class WebhookReplyIngestor:
    """Parses a list of provider-shaped webhook payloads in-memory.

    Configure `field_map` to remap source-key -> normalized-key.
    Default mapping covers the common shape used by Postmark / SendGrid /
    Mailgun-ish providers.
    """
    name: str = "webhook"
    payloads: list[dict] = field(default_factory=list)
    field_map: dict[str, str] = field(default_factory=lambda: {
        "MessageID": "message_id_external",
        "Message-Id": "message_id_external",
        "InReplyTo": "in_reply_to",
        "In-Reply-To": "in_reply_to",
        "From": "from_email",
        "FromName": "from_name",
        "Subject": "subject",
        "TextBody": "body",
        "HtmlBody": "body_html",
        "ReceivedAt": "received_at",
        "Date": "received_at",
    })

    def add(self, payload: dict) -> None:
        self.payloads.append(payload)

    def fetch(self, *, limit: int = 200) -> list[dict]:
        out: list[dict] = []
        items = self.payloads[:limit]
        self.payloads = self.payloads[limit:]
        for p in items:
            out.append(self._normalize(p))
        return out

    def _normalize(self, p: dict) -> dict:
        norm: dict[str, Any] = {
            "provider": self.name,
            "message_id_external": None,
            "in_reply_to": None,
            "from_email": None,
            "from_name": None,
            "subject": "",
            "body": "",
            "body_html": None,
            "received_at": None,
            "raw_response": p,
        }
        for src, dst in self.field_map.items():
            if src in p and p[src] is not None:
                norm[dst] = p[src]
        # Allow already-normalized keys to win
        for k in list(norm.keys()):
            if k in p and p[k] is not None:
                norm[k] = p[k]
        return norm


# ---------------------------------------------------------------------------
# Fake ingestor
# ---------------------------------------------------------------------------
@dataclass
class FakeReplyIngestor:
    name: str = "fake"
    payloads: list[dict] = field(default_factory=list)

    def add(self, payload: dict) -> None:
        self.payloads.append(payload)

    @classmethod
    def from_sends(
        cls,
        sends: Iterable[dict],
        *,
        body: str = "Sounds good, let's chat.",
        subject: str = "Re: outreach",
        from_email: str = "lead@example.com",
        intent_hint: Optional[str] = None,
    ) -> "FakeReplyIngestor":
        ing = cls()
        for s in sends:
            ing.add({
                "provider": "fake",
                "message_id_external": f"fake-reply-{s.get('id')}",
                "in_reply_to": s.get("message_id_external"),
                "from_email": from_email,
                "from_name": "Test Lead",
                "subject": subject,
                "body": body,
                "body_html": None,
                "received_at": _now_iso(),
                "raw_response": {"send_id": s.get("id"), "intent_hint": intent_hint},
            })
        return ing

    def fetch(self, *, limit: int = 200) -> list[dict]:
        items = self.payloads[:limit]
        self.payloads = self.payloads[limit:]
        return list(items)


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------
_default_ingestor: ReplyIngestor = FakeReplyIngestor()


def get_default_reply_ingestor() -> ReplyIngestor:
    return _default_ingestor


def set_default_reply_ingestor(ing: Optional[ReplyIngestor]) -> None:
    global _default_ingestor
    _default_ingestor = ing if ing is not None else FakeReplyIngestor()


def fetch_replies(
    *,
    limit: int = 200,
    ingestor: Optional[ReplyIngestor] = None,
) -> list[dict]:
    return (ingestor or _default_ingestor).fetch(limit=limit)
