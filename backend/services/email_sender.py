"""Pluggable EmailSender (File 15).

Implementations:
  - SMTPEmailSender:           reads env SMTP_HOST/PORT/USER/PASS/FROM/USE_TLS
  - FakeEmailSender:           deterministic fake-{message_id}-{n} for tests
  - LLMRewriteOnSendSender:    optional decorator that polishes body via LLM

Pluggable provider pattern (mirrors File 09..14):
    set_default_email_sender(fake)   # for tests
    get_default_email_sender()
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------
SEND_STATUSES = ("queued", "sending", "sent", "bounced", "failed", "opened", "replied")


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
class EmailSender(Protocol):
    name: str

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        body_html: Optional[str] = None,
        outreach_message_id: Optional[int] = None,
    ) -> dict:
        """Return {ok, provider, message_id_external, status, error?, raw_response}."""
        ...


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------
@dataclass
class SMTPEmailSender:
    name: str = "smtp"
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    from_addr: Optional[str] = None
    use_tls: Optional[bool] = None

    def __post_init__(self) -> None:
        self.host = self.host or os.environ.get("SMTP_HOST")
        port_env = os.environ.get("SMTP_PORT")
        if self.port is None and port_env:
            self.port = int(port_env)
        self.username = self.username or os.environ.get("SMTP_USER")
        self.password = self.password or os.environ.get("SMTP_PASS")
        self.from_addr = self.from_addr or os.environ.get("SMTP_FROM")
        if self.use_tls is None:
            self.use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        body_html: Optional[str] = None,
        outreach_message_id: Optional[int] = None,
    ) -> dict:
        if not self.host or not self.from_addr:
            return {
                "ok": False,
                "provider": self.name,
                "message_id_external": None,
                "status": "failed",
                "error": "smtp_not_configured",
                "raw_response": {"host": self.host, "from": self.from_addr},
            }
        try:
            import aiosmtplib
            from email.message import EmailMessage
        except Exception as exc:  # pragma: no cover - dependency missing
            return {
                "ok": False,
                "provider": self.name,
                "message_id_external": None,
                "status": "failed",
                "error": f"aiosmtplib_unavailable: {exc}",
                "raw_response": {},
            }

        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body or "")
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        external_id = msg.get("Message-ID") or f"smtp-{outreach_message_id}-{id(msg)}"
        try:
            response = asyncio.run(
                aiosmtplib.send(
                    msg,
                    hostname=self.host,
                    port=int(self.port or 587),
                    username=self.username,
                    password=self.password,
                    start_tls=bool(self.use_tls),
                )
            )
        except Exception as exc:
            err = str(exc).lower()
            status = "bounced" if ("bounce" in err or "5.1.1" in err or "no such user" in err) else "failed"
            return {
                "ok": False,
                "provider": self.name,
                "message_id_external": external_id,
                "status": status,
                "error": str(exc),
                "raw_response": {"exception": str(exc)},
            }
        return {
            "ok": True,
            "provider": self.name,
            "message_id_external": external_id,
            "status": "sent",
            "raw_response": {"smtp_response": str(response)},
        }


# ---------------------------------------------------------------------------
# Fake sender (deterministic)
# ---------------------------------------------------------------------------
@dataclass
class FakeEmailSender:
    name: str = "fake"
    counter: int = 0
    fail_on: tuple[str, ...] = ()
    bounce_on: tuple[str, ...] = ()

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        body_html: Optional[str] = None,
        outreach_message_id: Optional[int] = None,
    ) -> dict:
        self.counter += 1
        external_id = f"fake-{outreach_message_id}-{self.counter}"
        if to in self.bounce_on:
            return {
                "ok": False,
                "provider": self.name,
                "message_id_external": external_id,
                "status": "bounced",
                "error": "fake_bounce",
                "raw_response": {"fake": True, "to": to},
            }
        if to in self.fail_on:
            return {
                "ok": False,
                "provider": self.name,
                "message_id_external": external_id,
                "status": "failed",
                "error": "fake_failure",
                "raw_response": {"fake": True, "to": to},
            }
        return {
            "ok": True,
            "provider": self.name,
            "message_id_external": external_id,
            "status": "sent",
            "raw_response": {"fake": True, "to": to, "subject": subject},
        }


# ---------------------------------------------------------------------------
# LLM rewrite decorator
# ---------------------------------------------------------------------------
@dataclass
class LLMRewriteOnSendSender:
    """Polishes the body via LLM before delegating to a base sender.

    Degrades to base sender unchanged when llm is None.
    """
    base: EmailSender
    llm: Any = None
    model: str = "gpt-4o-mini"
    name: str = "llm_rewrite"

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        body_html: Optional[str] = None,
        outreach_message_id: Optional[int] = None,
    ) -> dict:
        new_subject = subject
        new_body = body
        if self.llm is not None:
            try:
                prompt = (
                    "Polish this outbound email for clarity and warmth. "
                    'Reply JSON {"subject": str, "body": str}. '
                    f"Subject: {subject!r}\nBody:\n{body}"
                )
                resp, _usage = self.llm.call_openai_tools(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model, response_format="json",
                )
                new_subject = str((resp or {}).get("subject") or subject)
                new_body = str((resp or {}).get("body") or body)
            except Exception:  # pragma: no cover - defensive
                pass
        return self.base.send(
            to=to,
            subject=new_subject,
            body=new_body,
            body_html=body_html,
            outreach_message_id=outreach_message_id,
        )


# ---------------------------------------------------------------------------
# SendGrid sender
# ---------------------------------------------------------------------------
@dataclass
class SendGridEmailSender:
    name: str = "sendgrid"
    api_key: Optional[str] = None
    from_addr: Optional[str] = None
    from_name: Optional[str] = None

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("SENDGRID_API_KEY")
        self.from_addr = self.from_addr or os.environ.get("SENDGRID_FROM") or os.environ.get("SMTP_FROM")
        self.from_name = self.from_name or os.environ.get("SENDGRID_FROM_NAME")

    def send(self, *, to: str, subject: str, body: str, body_html: Optional[str] = None,
             outreach_message_id: Optional[int] = None) -> dict:
        if not self.api_key or not self.from_addr:
            return {"ok": False, "provider": self.name, "message_id_external": None,
                    "status": "failed", "error": "sendgrid_not_configured", "raw_response": {}}
        try:
            import httpx
        except Exception as exc:
            return {"ok": False, "provider": self.name, "message_id_external": None,
                    "status": "failed", "error": f"httpx_unavailable: {exc}", "raw_response": {}}
        from_field: dict = {"email": self.from_addr}
        if self.from_name:
            from_field["name"] = self.from_name
        content = [{"type": "text/plain", "value": body or ""}]
        if body_html:
            content.append({"type": "text/html", "value": body_html})
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": from_field,
            "subject": subject,
            "content": content,
        }
        try:
            r = httpx.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json=payload, timeout=20.0,
            )
            ext = r.headers.get("X-Message-Id") or f"sg-{outreach_message_id}"
            if 200 <= r.status_code < 300:
                return {"ok": True, "provider": self.name, "message_id_external": ext,
                        "status": "sent", "raw_response": {"status_code": r.status_code}}
            return {"ok": False, "provider": self.name, "message_id_external": ext,
                    "status": "failed", "error": f"http_{r.status_code}",
                    "raw_response": {"body": r.text[:500]}}
        except Exception as exc:
            return {"ok": False, "provider": self.name, "message_id_external": None,
                    "status": "failed", "error": str(exc), "raw_response": {}}


# ---------------------------------------------------------------------------
# Postmark sender
# ---------------------------------------------------------------------------
@dataclass
class PostmarkEmailSender:
    name: str = "postmark"
    server_token: Optional[str] = None
    from_addr: Optional[str] = None
    message_stream: str = "outbound"

    def __post_init__(self) -> None:
        self.server_token = self.server_token or os.environ.get("POSTMARK_SERVER_TOKEN")
        self.from_addr = self.from_addr or os.environ.get("POSTMARK_FROM") or os.environ.get("SMTP_FROM")
        self.message_stream = os.environ.get("POSTMARK_STREAM", self.message_stream)

    def send(self, *, to: str, subject: str, body: str, body_html: Optional[str] = None,
             outreach_message_id: Optional[int] = None) -> dict:
        if not self.server_token or not self.from_addr:
            return {"ok": False, "provider": self.name, "message_id_external": None,
                    "status": "failed", "error": "postmark_not_configured", "raw_response": {}}
        try:
            import httpx
        except Exception as exc:
            return {"ok": False, "provider": self.name, "message_id_external": None,
                    "status": "failed", "error": f"httpx_unavailable: {exc}", "raw_response": {}}
        payload: dict = {
            "From": self.from_addr,
            "To": to,
            "Subject": subject,
            "TextBody": body or "",
            "MessageStream": self.message_stream,
        }
        if body_html:
            payload["HtmlBody"] = body_html
        try:
            r = httpx.post(
                "https://api.postmarkapp.com/email",
                headers={"Accept": "application/json", "Content-Type": "application/json",
                         "X-Postmark-Server-Token": self.server_token},
                json=payload, timeout=20.0,
            )
            data = {}
            try:
                data = r.json()
            except Exception:
                pass
            ext = data.get("MessageID") or f"pm-{outreach_message_id}"
            if 200 <= r.status_code < 300 and data.get("ErrorCode", 0) == 0:
                return {"ok": True, "provider": self.name, "message_id_external": ext,
                        "status": "sent", "raw_response": data}
            return {"ok": False, "provider": self.name, "message_id_external": ext,
                    "status": "failed", "error": data.get("Message") or f"http_{r.status_code}",
                    "raw_response": data}
        except Exception as exc:
            return {"ok": False, "provider": self.name, "message_id_external": None,
                    "status": "failed", "error": str(exc), "raw_response": {}}


# ---------------------------------------------------------------------------
# Factory: choose sender based on env (EMAIL_PROVIDER=fake|smtp|sendgrid|postmark)
# ---------------------------------------------------------------------------
def build_sender_from_env() -> "EmailSender":
    provider = (os.environ.get("EMAIL_PROVIDER") or "fake").strip().lower()
    if provider == "smtp":
        return SMTPEmailSender()
    if provider == "sendgrid":
        return SendGridEmailSender()
    if provider == "postmark":
        return PostmarkEmailSender()
    return FakeEmailSender()


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------
_default_sender: EmailSender = FakeEmailSender()


def get_default_email_sender() -> EmailSender:
    return _default_sender


def set_default_email_sender(sender: Optional[EmailSender]) -> None:
    global _default_sender
    _default_sender = sender if sender is not None else FakeEmailSender()


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    body_html: Optional[str] = None,
    outreach_message_id: Optional[int] = None,
    sender: Optional[EmailSender] = None,
) -> dict:
    return (sender or _default_sender).send(
        to=to,
        subject=subject,
        body=body,
        body_html=body_html,
        outreach_message_id=outreach_message_id,
    )
