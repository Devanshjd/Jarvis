"""
J.A.R.V.I.S -- Email Plugin
Read, send, and manage emails directly from JARVIS.

Commands:
    /inbox [count]                     -- Check inbox (default last 5)
    /readmail <id>                     -- Read a specific email
    /sendmail <to> <subject> | <body>  -- Send an email
    /draftemail <to> <subject> | <body> -- Save as draft
    /drafts                            -- List saved drafts
    /emailsetup [provider email pass]  -- Configure email
"""

import imaplib
import smtplib
import email
import email.header
import email.mime.text
import email.mime.multipart
import re
import threading
from datetime import datetime

from core.plugin_manager import PluginBase
from core.config import save_config


PROVIDERS = {
    "gmail": {
        "imap_server": "imap.gmail.com", "imap_port": 993,
        "smtp_server": "smtp.gmail.com", "smtp_port": 587,
    },
    "outlook": {
        "imap_server": "outlook.office365.com", "imap_port": 993,
        "smtp_server": "smtp.office365.com", "smtp_port": 587,
    },
    "yahoo": {
        "imap_server": "imap.mail.yahoo.com", "imap_port": 993,
        "smtp_server": "smtp.mail.yahoo.com", "smtp_port": 587,
    },
}


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    for entity, char in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"')]:
        text = text.replace(entity, char)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode_header(raw):
    parts = email.header.decode_header(raw or "")
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _get_body(msg) -> str:
    if msg.is_multipart():
        plain = html = None
        for part in msg.walk():
            ctype = part.get_content_type()
            if "attachment" in str(part.get("Content-Disposition", "")):
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if ctype == "text/plain" and not plain:
                plain = text
            elif ctype == "text/html" and not html:
                html = text
        if plain:
            return plain[:2000]
        if html:
            return _strip_html(html)[:2000]
        return "(No readable body)"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                text = _strip_html(text)
            return text[:2000]
        return "(Empty message)"


class EmailPlugin(PluginBase):
    name = "email"
    description = "Email -- read, send, and draft emails via IMAP/SMTP"
    version = "1.0"

    def activate(self):
        if "email" not in self.jarvis.config:
            self.jarvis.config["email"] = {}
        if "email_drafts" not in self.jarvis.config:
            self.jarvis.config["email_drafts"] = []

    def deactivate(self):
        pass

    def _cfg(self):
        return self.jarvis.config.get("email", {})

    def _is_configured(self) -> bool:
        cfg = self._cfg()
        return bool(cfg.get("address") and cfg.get("password")
                     and cfg.get("imap_server") and cfg.get("smtp_server"))

    def _msg(self, role, text):
        self.jarvis.root.after(0,
            lambda: self.jarvis.chat.add_message(role, text))

    def _bg(self, func, *args):
        def _run():
            try:
                result = func(*args)
                if result:
                    self._msg("assistant", result)
            except Exception as e:
                self._msg("system", f"Email error: {e}")
        threading.Thread(target=_run, daemon=True).start()

    # ── IMAP / SMTP ─────────────────────────────────────────────

    def _imap_connect(self):
        cfg = self._cfg()
        mail = imaplib.IMAP4_SSL(cfg["imap_server"], int(cfg.get("imap_port", 993)))
        mail.login(cfg["address"], cfg["password"])
        return mail

    def _smtp_send(self, to_addr, subject, body):
        cfg = self._cfg()
        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = cfg["address"]
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(email.mime.text.MIMEText(body, "plain"))
        with smtplib.SMTP(cfg["smtp_server"], int(cfg.get("smtp_port", 587))) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["address"], cfg["password"])
            server.sendmail(cfg["address"], to_addr, msg.as_string())

    # ── Operations ──────────────────────────────────────────────

    def _fetch_inbox(self, count=5):
        mail = self._imap_connect()
        mail.select("INBOX", readonly=True)
        status, data = mail.search(None, "ALL")
        if status != "OK":
            mail.logout()
            return "Failed to search inbox."
        ids = data[0].split()
        if not ids:
            mail.logout()
            return "Your inbox is empty, sir."

        latest = ids[-count:]
        latest.reverse()

        lines = [f"Inbox -- Last {len(latest)} Emails\n{'=' * 50}"]
        for i, uid in enumerate(latest, 1):
            status, msg_data = mail.fetch(uid, "(RFC822.HEADER)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            frm = _decode_header(msg.get("From", "?"))
            subj = _decode_header(msg.get("Subject", "(no subject)"))
            date = msg.get("Date", "")[:22]
            if "<" in frm:
                name = frm.split("<")[0].strip().strip('"')
                frm = name if name else frm
            if len(frm) > 30:
                frm = frm[:28] + ".."
            if len(subj) > 45:
                subj = subj[:43] + ".."
            lines.append(f"\n[{uid.decode()}] {subj}\n     From: {frm}  |  {date}")

        mail.logout()
        lines.append(f"\nUse /readmail <id> to read full email.")
        return "\n".join(lines)

    def _read_mail(self, mail_id):
        mail = self._imap_connect()
        mail.select("INBOX", readonly=True)
        status, msg_data = mail.fetch(mail_id.encode(), "(RFC822)")
        if status != "OK":
            mail.logout()
            return f"Could not fetch email #{mail_id}."
        msg = email.message_from_bytes(msg_data[0][1])
        mail.logout()

        return (
            f"Email #{mail_id}\n{'=' * 50}\n"
            f"From:    {_decode_header(msg.get('From', '?'))}\n"
            f"To:      {_decode_header(msg.get('To', '?'))}\n"
            f"Date:    {msg.get('Date', '?')}\n"
            f"Subject: {_decode_header(msg.get('Subject', ''))}\n"
            f"{'=' * 50}\n\n{_get_body(msg)}"
        )

    def _send_email(self, to_addr, subject, body):
        self._smtp_send(to_addr, subject, body)
        return f"Email sent successfully, sir.\n  To: {to_addr}\n  Subject: {subject}"

    def _read_latest(self):
        mail = self._imap_connect()
        mail.select("INBOX", readonly=True)
        status, data = mail.search(None, "ALL")
        if status != "OK" or not data[0].split():
            mail.logout()
            return "No emails found."
        latest_id = data[0].split()[-1]
        mail.logout()
        return self._read_mail(latest_id.decode())

    def _parse_mail_args(self, args):
        args = args.strip()
        if not args:
            return None
        parts = args.split(None, 1)
        if len(parts) < 2:
            return None
        to_addr = parts[0]
        rest = parts[1]
        if "|" in rest:
            subject, body = rest.split("|", 1)
            return to_addr, subject.strip(), body.strip()
        return to_addr, rest.strip(), ""

    # ── Commands ────────────────────────────────────────────────

    def on_command(self, command: str, args: str) -> bool:
        cmd = command.lower()

        if cmd == "/emailsetup":
            if args.strip():
                self._apply_setup(args)
            else:
                self._show_setup()
            return True

        if cmd == "/inbox":
            if not self._is_configured():
                self._msg("system", "Email not configured. Run /emailsetup")
                return True
            count = int(args.strip()) if args.strip().isdigit() else 5
            self._msg("system", "Checking inbox...")
            self._bg(self._fetch_inbox, min(count, 50))
            return True

        if cmd == "/readmail":
            if not self._is_configured():
                self._msg("system", "Email not configured. Run /emailsetup")
                return True
            if not args.strip():
                self._msg("system", "Usage: /readmail <id>")
                return True
            self._bg(self._read_mail, args.strip())
            return True

        if cmd == "/sendmail":
            if not self._is_configured():
                self._msg("system", "Email not configured. Run /emailsetup")
                return True
            parsed = self._parse_mail_args(args)
            if not parsed:
                self._msg("system", "Usage: /sendmail to@email.com Subject | Body")
                return True
            self._msg("system", f"Sending to {parsed[0]}...")
            self._bg(self._send_email, *parsed)
            return True

        if cmd == "/draftemail":
            parsed = self._parse_mail_args(args)
            if not parsed:
                self._msg("system", "Usage: /draftemail to@email.com Subject | Body")
                return True
            draft = {"to": parsed[0], "subject": parsed[1], "body": parsed[2],
                     "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
            self.jarvis.config["email_drafts"].append(draft)
            save_config(self.jarvis.config)
            self._msg("assistant", f"Draft saved.\n  To: {parsed[0]}\n  Subject: {parsed[1]}")
            return True

        if cmd == "/drafts":
            drafts = self.jarvis.config.get("email_drafts", [])
            if not drafts:
                self._msg("assistant", "No drafts saved, sir.")
                return True
            lines = ["Saved Drafts\n" + "=" * 30]
            for i, d in enumerate(drafts, 1):
                lines.append(f"\n[{i}] To: {d['to']}\n    Subject: {d['subject']}\n    Created: {d.get('created', '?')}")
            self._msg("assistant", "\n".join(lines))
            return True

        return False

    # ── Natural language ────────────────────────────────────────

    def on_message(self, message: str) -> str | None:
        msg = message.lower().strip()

        if re.search(r"(?:check|show|get|open)\s+(?:my\s+)?(?:email|inbox|mail)", msg):
            if not self._is_configured():
                self._msg("system", "Email not configured. Run /emailsetup")
                return "__handled__"
            self._msg("system", "Checking inbox...")
            self._bg(self._fetch_inbox, 5)
            return "__handled__"

        if re.search(r"(?:any|do i have)\s+(?:new\s+)?(?:email|mail)", msg):
            if not self._is_configured():
                self._msg("system", "Email not configured. Run /emailsetup")
                return "__handled__"
            self._bg(self._fetch_inbox, 5)
            return "__handled__"

        if re.search(r"read\s+(?:my\s+)?(?:latest|last|recent)\s+(?:email|mail)", msg):
            if not self._is_configured():
                self._msg("system", "Email not configured. Run /emailsetup")
                return "__handled__"
            self._bg(self._read_latest)
            return "__handled__"

        return None

    # ── Setup ───────────────────────────────────────────────────

    def _show_setup(self):
        cfg = self._cfg()
        status = f"Configured: {cfg.get('address', 'N/A')}" if self._is_configured() else "Not configured"
        self._msg("assistant",
            f"Email Setup\n{'=' * 30}\n\n"
            f"Status: {status}\n\n"
            f"Configure with:\n"
            f"  /emailsetup <provider> <email> <app_password>\n\n"
            f"Providers: gmail, outlook, yahoo\n\n"
            f"Example:\n"
            f"  /emailsetup gmail your@gmail.com abcdefghijklmnop\n\n"
            f"For Gmail:\n"
            f"  1. Enable 2-Step Verification\n"
            f"  2. Go to myaccount.google.com/apppasswords\n"
            f"  3. Generate App Password for 'Mail'\n"
            f"  4. Use that 16-char password here\n\n"
            f"Your password is stored locally only.")

    def _apply_setup(self, args):
        parts = args.strip().split(None, 2)
        if len(parts) < 3:
            self._msg("system", "Usage: /emailsetup <provider> <email> <password>")
            return
        provider, addr, password = parts[0].lower(), parts[1], parts[2]
        if provider not in PROVIDERS:
            self._msg("system", f"Unknown provider '{provider}'. Use: gmail, outlook, yahoo")
            return
        preset = PROVIDERS[provider]
        self.jarvis.config["email"] = {
            "provider": provider, "address": addr, "password": password,
            **preset,
        }
        save_config(self.jarvis.config)
        self._msg("system", f"Email configured for {addr}. Testing...")
        self._bg(self._test_connection)

    def _test_connection(self):
        try:
            mail = self._imap_connect()
            mail.logout()
            return "Connection successful! Try /inbox to check emails."
        except Exception as e:
            return (f"Connection failed: {e}\n\n"
                    "For Gmail: Use App Password, not regular password.\n"
                    "Run /emailsetup again to reconfigure.")

    def get_status(self) -> dict:
        return {
            "name": self.name, "active": True,
            "configured": self._is_configured(),
        }
