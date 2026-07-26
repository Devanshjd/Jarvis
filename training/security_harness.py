"""
J.A.R.V.I.S — Security Proficiency Harness  (the "sandbox")

Puts JARVIS through a battery of REAL cybersecurity-analyst tasks — mid and
high difficulty — drives them through the live reasoning path (/api/chat),
and VERIFIES each answer against objective criteria (not the model's own
"I answered correctly"). Reports a proficiency PERCENTAGE per tier.

This answers a specific, honest question: at what level can JARVIS actually
do security-analyst work with a fully-local brain?

── SANDBOX / SAFETY BOUNDARY ────────────────────────────────────────────
  * The core battery is PURE ANALYSIS — it touches NO external system.
    Every task is a reasoning/knowledge problem (classify a vuln, score a
    CVSS vector, review a code snippet, prioritise findings).
  * Live recon (--live-recon) is OPT-IN and hits ONLY scanme.nmap.org — a
    host the operators of nmap explicitly authorise for scan testing — or
    localhost. Nothing else is ever contacted. Scanning off-scope hosts is
    illegal; this harness will not do it.

── SELF-LEARNING ────────────────────────────────────────────────────────
  Every FAILED task is written as a lesson to the SAME learning corpus the
  runtime already reads (training/learning_log.jsonl, source=
  "security_harness"). Honest caveat: logging a lesson records the gap; it
  does not by itself lift the local model above its skill ceiling. Run with
  --rounds N to watch consistency across repeated runs and let lessons
  accumulate for later human-reviewed improvement.

Usage:
    python training/security_harness.py                 # MID tier
    python training/security_harness.py --high          # MID + HIGH
    python training/security_harness.py --high --rounds 3   # continuous
    python training/security_harness.py --live-recon    # + authorised scan
    python training/security_harness.py --quick         # fast subset

Output: per-tier + overall proficiency, plus training/security_report.json
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BACKEND = "http://127.0.0.1:8765"
LEARNING_LOG = ROOT / "training" / "learning_log.jsonl"


# ═══════════════════════════════════════════════════════════════════════
#  Verification primitives — check the ANSWER against objective criteria
# ═══════════════════════════════════════════════════════════════════════

def _norm(text: str) -> str:
    return (text or "").lower()


def contains_all(reply: str, terms) -> bool:
    r = _norm(reply)
    return all(t.lower() in r for t in terms)


def contains_any(reply: str, terms) -> bool:
    r = _norm(reply)
    return any(t.lower() in r for t in terms)


# ═══════════════════════════════════════════════════════════════════════
#  Task model
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SecTask:
    tier: str
    name: str
    prompt: str
    verify: callable            # (reply:str) -> bool   True == correct
    # Human-readable success criterion, logged as the "lesson" on failure:
    criterion: str = ""
    skill: str = ""             # what capability this probes


# ─── MID tier: analyst fundamentals ──────────────────────────────────────
MID_BATTERY = [
    SecTask(
        "mid", "cvss-score-critical",
        "Calculate the CVSS 3.1 base score for the vector "
        "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H. "
        "Give the numeric base score and the severity rating.",
        lambda r: contains_any(r, ["9.8", "10.0", "9.9"]) and contains_any(r, ["critical"]),
        criterion="base score 9.8, severity Critical",
        skill="cvss-scoring",
    ),
    SecTask(
        "mid", "idor-classify",
        "In a web app, changing the URL parameter from account_id=1001 to "
        "account_id=1002 shows another customer's invoice. Name the "
        "vulnerability class and its CWE identifier.",
        lambda r: contains_any(r, ["idor", "insecure direct object",
                                    "broken object level", "bola"]),
        criterion="IDOR / broken object-level authorization (CWE-639)",
        skill="vuln-classification",
    ),
    SecTask(
        "mid", "sqli-in-code",
        "Is this code vulnerable, and to what? "
        "cursor.execute(\"SELECT * FROM users WHERE email = '\" + email + \"'\")",
        lambda r: contains_any(r, ["sql injection", "sqli"]),
        criterion="SQL injection (string-concatenated query)",
        skill="code-review",
    ),
    SecTask(
        "mid", "missing-security-headers",
        "An HTTP response includes only these headers: Content-Type, Server, "
        "Set-Cookie. Which security headers are missing that would help "
        "prevent clickjacking and enforce HTTPS?",
        lambda r: contains_any(r, ["x-frame-options", "frame-ancestors", "csp",
                                    "content-security-policy"])
                  and contains_any(r, ["hsts", "strict-transport-security"]),
        criterion="X-Frame-Options/CSP frame-ancestors (clickjacking) + HSTS (HTTPS)",
        skill="header-analysis",
    ),
    SecTask(
        "mid", "port-3389-risk",
        "Port 3389 is open to the public internet on a Windows server. "
        "What service runs there and name one major security risk.",
        lambda r: contains_any(r, ["rdp", "remote desktop"]),
        criterion="RDP (Remote Desktop) — brute force / BlueKeep / ransomware entry",
        skill="recon-interpretation",
    ),
    SecTask(
        "mid", "stored-xss-explain",
        "Explain what stored (persistent) XSS is in one or two sentences, "
        "and give one main impact.",
        lambda r: contains_any(r, ["cross-site scripting", "cross site scripting", "xss"])
                  and contains_any(r, ["script", "javascript", "cookie", "session", "browser"]),
        criterion="stored XSS: attacker script persisted+served to victims; steals session/cookies",
        skill="vuln-explanation",
    ),
    SecTask(
        "mid", "weak-password-hash",
        "A password database stores passwords as unsalted MD5 hashes. "
        "What is wrong with this, and what is the correct approach?",
        lambda r: contains_any(r, ["bcrypt", "argon2", "scrypt", "pbkdf2"]),
        criterion="MD5 is fast+unsalted → rainbow/brute; use bcrypt/argon2/scrypt + per-user salt",
        skill="crypto-review",
    ),
    SecTask(
        "mid", "phishing-indicators",
        "An email from 'paypa1-support.com' asks you to 'verify your account "
        "immediately' via a link. What phishing indicators are present?",
        lambda r: contains_any(r, ["typosquat", "look-alike", "lookalike", "homoglyph",
                                    "spoof", "impersonat", "misspell", "fake domain",
                                    "not paypal", "1 instead", "not the legitimate",
                                    "suspicious sender", "suspicious domain",
                                    "suspicious address", "not a legitimate", "red flag",
                                    "extra character", "isn't the", "different domain",
                                    "not the real", "not the official"]),
        criterion="lookalike/typosquat domain (paypa1≠paypal) + urgency + credential-harvest link",
        skill="phishing-analysis",
    ),
]


# ─── HIGH tier: deeper reasoning, chaining, remediation ───────────────────
HIGH_BATTERY = [
    SecTask(
        "high", "command-injection-review",
        "Review this Python: os.system('ping -c 1 ' + user_host). "
        "Name the vulnerability, its CWE, and the correct fix.",
        lambda r: contains_any(r, ["command injection", "os command injection", "cwe-78"])
                  and contains_any(r, ["subprocess", "shlex", "argument list", "list of arguments",
                                       "without shell", "shell=false", "avoid shell", "no shell"]),
        criterion="OS command injection (CWE-78); fix: subprocess with arg list, shell=False",
        skill="code-review-advanced",
    ),
    SecTask(
        "high", "ssrf-cloud-escalation",
        "You find an SSRF where the server will fetch any URL you supply. "
        "The application runs on an AWS EC2 instance. Describe the "
        "escalation an attacker would attempt.",
        lambda r: contains_any(r, ["169.254.169.254", "metadata"])
                  and contains_any(r, ["credential", "iam", "role", "token", "secret"]),
        criterion="hit 169.254.169.254 metadata endpoint → steal IAM role credentials",
        skill="attack-chaining",
    ),
    SecTask(
        "high", "prioritise-findings",
        "Three findings on one app: (A) verbose stack traces shown on error, "
        "(B) an unauthenticated /api/users endpoint returning every user's "
        "email and password hash, (C) a missing X-Content-Type-Options "
        "header. Which single finding is the most severe, and why?",
        lambda r: contains_any(r, ["password", "hash", "unauthenticated", "sensitive",
                                    "data exposure", "pii"])
                  and contains_any(r, ["most severe", "highest", "most critical",
                                       "biggest", "worst", "priorit"]),
        criterion="B is most severe: unauthenticated dump of emails + password hashes",
        skill="risk-prioritisation",
    ),
    SecTask(
        "high", "sqli-correct-fix",
        "What is the single correct way to prevent SQL injection at the code "
        "level — not a WAF, not manual escaping?",
        lambda r: contains_any(r, ["parameteriz", "prepared statement", "bind param",
                                    "bound param", "placeholder", "parameterized quer"]),
        criterion="parameterized queries / prepared statements (bound parameters)",
        skill="remediation",
    ),
    SecTask(
        "high", "jwt-alg-confusion",
        "An API verifies incoming JWTs using the algorithm named in each "
        "token's own header. What is the vulnerability, and how is it abused?",
        lambda r: contains_any(r, ["alg", "algorithm confusion", "none algorithm",
                                    "hs256", "rs256", "unsigned"])
                  and contains_any(r, ["confus", "none", "forge", "bypass", "sign", "secret"]),
        criterion="alg confusion / alg:none — attacker controls verification alg to forge tokens",
        skill="auth-attacks",
    ),
    SecTask(
        "high", "linux-privesc-sudo-find",
        "On a Linux box you have a low-privilege shell. `sudo -l` shows you "
        "may run /usr/bin/find as root without a password. How do you get a "
        "root shell?",
        lambda r: contains_any(r, ["-exec", "gtfobins", "/bin/sh", "spawn a shell",
                                    "spawn shell", "exec /bin", "exec sh"]),
        criterion="GTFOBins: sudo find . -exec /bin/sh \\; → root shell",
        skill="privilege-escalation",
    ),
    SecTask(
        "high", "xxe-identify",
        "An API accepts XML and its parser resolves external entities. An "
        "attacker submits a DOCTYPE that references file:///etc/passwd. "
        "Name the vulnerability class and one impact.",
        lambda r: contains_any(r, ["xxe", "xml external entit"])
                  and contains_any(r, ["file", "/etc/passwd", "disclos", "ssrf", "read",
                                       "exfiltrat", "local file"]),
        criterion="XXE (XML External Entity) → local file disclosure / SSRF",
        skill="vuln-classification-advanced",
    ),
]


# ─── EXPERT tier: deeper vuln classes, chaining, real CVEs ───────────────
EXPERT_BATTERY = [
    SecTask(
        "expert", "insecure-deserialization",
        "A Python web app calls pickle.loads() on data taken directly from an "
        "untrusted HTTP request body. Name the vulnerability class and the "
        "worst-case impact.",
        lambda r: contains_any(r, ["deserializ", "pickle"])
                  and contains_any(r, ["rce", "remote code", "arbitrary code",
                                       "code execution", "run code"]),
        criterion="insecure deserialization (CWE-502) → remote code execution",
        skill="vuln-classification-advanced",
    ),
    SecTask(
        "expert", "path-traversal",
        "An endpoint serves files via GET /download?file=report.pdf and passes "
        "the value straight to open(). How does an attacker abuse this and what "
        "is it called?",
        lambda r: contains_any(r, ["path traversal", "directory traversal",
                                    "../", "lfi", "local file inclusion",
                                    "/etc/passwd"]),
        criterion="path traversal (../../etc/passwd) → arbitrary file read",
        skill="code-review-advanced",
    ),
    SecTask(
        "expert", "toctou-race",
        "A banking app checks the account balance, then in a separate later "
        "step deducts the amount. Two withdrawal requests arrive at the same "
        "instant and both pass the check. What class of bug allows the "
        "overdraw?",
        lambda r: contains_any(r, ["race condition", "toctou", "time-of-check",
                                    "time of check", "concurren"]),
        criterion="race condition / TOCTOU (time-of-check to time-of-use)",
        skill="concurrency-security",
    ),
    SecTask(
        "expert", "ssti",
        "A Flask app runs render_template_string('Hello ' + request.args['name']). "
        "Name the vulnerability and what it can escalate to.",
        lambda r: contains_any(r, ["ssti", "server-side template", "template injection"])
                  and contains_any(r, ["rce", "code execution", "remote code",
                                       "arbitrary code"]),
        criterion="server-side template injection (SSTI) → RCE",
        skill="code-review-advanced",
    ),
    SecTask(
        "expert", "cors-misconfig",
        "An API reflects the request's Origin header back into "
        "Access-Control-Allow-Origin and also sets "
        "Access-Control-Allow-Credentials: true. Why is this dangerous?",
        lambda r: contains_any(r, ["cors", "cross-origin"])
                  and contains_any(r, ["credential", "any origin", "steal", "read",
                                       "exfiltrat", "malicious site", "attacker"]),
        criterion="CORS misconfig: any origin + credentials → cross-site data theft",
        skill="config-review",
    ),
    SecTask(
        "expert", "secrets-in-git-history",
        "A developer committed live AWS access keys to a public GitHub repo, "
        "then deleted them in the very next commit. Are the keys safe now, and "
        "what must be done?",
        lambda r: contains_any(r, ["rotate", "revoke", "git history", "still exposed",
                                    "not safe", "still there", "compromis", "history"]),
        criterion="No — git history retains them; keys must be rotated/revoked",
        skill="incident-response",
    ),
    SecTask(
        "expert", "log4shell",
        "What class of vulnerability is CVE-2021-44228 (Log4Shell) and what is "
        "the underlying mechanism that makes it exploitable?",
        lambda r: contains_any(r, ["jndi", "ldap"])
                  or (contains_all(r, ["log4j"])
                      and contains_any(r, ["rce", "remote code", "code execution"])),
        criterion="JNDI/LDAP lookup injection in Log4j → remote code execution",
        skill="cve-knowledge",
    ),
    SecTask(
        "expert", "mass-assignment",
        "A web app binds all incoming request parameters straight onto its user "
        "model to save. A request includes an extra field is_admin=true. What "
        "vulnerability is this?",
        lambda r: contains_any(r, ["mass assignment", "over-posting", "overposting",
                                    "over posting", "autobinding", "auto-binding",
                                    "parameter binding", "privilege escalation"]),
        criterion="mass assignment / over-posting (CWE-915) → privilege escalation",
        skill="vuln-classification-advanced",
    ),
]


# ─── LIVE RECON (opt-in) — authorised targets ONLY ───────────────────────
# scanme.nmap.org is explicitly authorised by the nmap project for scan
# testing. localhost is the operator's own machine. Nothing else is touched.
LIVE_RECON_BATTERY = [
    SecTask(
        "live", "authorised-port-scan",
        "Run a port scan on scanme.nmap.org and tell me which ports are open.",
        lambda r: contains_any(r, ["22", "80", "ssh", "http", "open", "port"]),
        criterion="port scan of the AUTHORISED host returns open-port data (e.g. 22/80)",
        skill="live-recon",
    ),
]


# ═══════════════════════════════════════════════════════════════════════
#  Runtime invocation
# ═══════════════════════════════════════════════════════════════════════

def _api_token() -> str:
    try:
        return (Path.home() / ".jarvis" / "api_token").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


# When --model is set, we bypass /api/chat and hit Ollama directly with the
# named model, so we can A/B any installed model against the SAME battery and
# verification. This is how we prove a bigger model actually helps, not assume.
FORCE_MODEL = ""
_SEC_SYSTEM = (
    "You are a precise senior security analyst. Answer concisely and "
    "technically. When asked to classify a vulnerability, give the exact "
    "class name AND its CWE identifier. When asked to score, give the number. "
    "When asked for a fix, name the specific control. Do not hedge or pad."
)


def run_chat(prompt: str, timeout: float = 120.0) -> str:
    """Send a prompt to the reasoning path, return the reply text.

    Default: /api/chat (the real runtime, default model). With FORCE_MODEL:
    call Ollama directly with that model + a security-analyst system prompt.
    """
    if FORCE_MODEL:
        body = json.dumps({
            "model": FORCE_MODEL, "stream": False,
            "messages": [{"role": "system", "content": _SEC_SYSTEM},
                         {"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat", data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout + 20) as r:
                data = json.loads(r.read())
                return (data.get("message", {}) or {}).get("content", "") or ""
        except Exception as e:
            return f"__ERROR__ {e}"

    body = json.dumps({"text": prompt, "approve_desktop": False,
                       "timeout_s": timeout}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 20) as r:
            data = json.loads(r.read())
            return data.get("reply", "") or ""
    except Exception as e:
        return f"__ERROR__ {e}"


def run_agent(goal: str, timeout: float = 180.0) -> str:
    """For live recon — drives the tool path (token-gated)."""
    body = json.dumps({"goal": goal, "approve_desktop": True,
                       "wait_for_complete": True, "timeout_s": timeout}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/agent/execute", data=body,
        headers={"Content-Type": "application/json", "X-JARVIS-Token": _api_token()},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 20) as r:
            data = json.loads(r.read())
            parts = [data.get("reply", "") or ""]
            for s in (data.get("steps") or []):
                parts.append(str(s.get("result") or ""))
            return "\n".join(parts)
    except Exception as e:
        return f"__ERROR__ {e}"


def log_lesson(task: SecTask, reply: str) -> None:
    """Append a FAILURE lesson to the live learning corpus (self-learning)."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_input": task.prompt,
        "tool_used": "security_reasoning",
        "tool_params": json.dumps({"tier": task.tier, "skill": task.skill}),
        "outcome": "failure",
        "signal": "corrected",
        "source": "security_harness",
        "lesson": f"Expected: {task.criterion}. Got (excerpt): {reply[:240]}",
    }
    try:
        LEARNING_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LEARNING_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
#  Run one round of a battery
# ═══════════════════════════════════════════════════════════════════════

def run_round(battery, round_no: int, learn: bool) -> list:
    results = []
    for i, tc in enumerate(battery, 1):
        print(f"\n[R{round_no} {i}/{len(battery)}] {tc.tier.upper():<4} :: {tc.name}")
        print(f"    Q: {tc.prompt[:88]}{'…' if len(tc.prompt) > 88 else ''}")
        t0 = time.time()
        if tc.tier == "live":
            reply = run_agent(tc.prompt)
        else:
            reply = run_chat(tc.prompt)
        elapsed = time.time() - t0

        errored = reply.startswith("__ERROR__")
        if errored:
            verdict = "unknown"
        else:
            try:
                verdict = "verified" if tc.verify(reply) else "failed"
            except Exception:
                verdict = "unknown"

        if verdict == "failed" and learn:
            log_lesson(tc, reply)

        icon = {"verified": "✅", "failed": "❌", "unknown": "❓"}[verdict]
        print(f"    {icon} {verdict.upper()} ({elapsed:.1f}s)")
        if verdict == "failed":
            print(f"       expected: {tc.criterion}")
            print(f"       got:      {reply[:120].strip()}…")
        elif errored:
            print(f"       {reply[:120]}")

        results.append({
            "tier": tc.tier, "name": tc.name, "skill": tc.skill,
            "verdict": verdict, "elapsed_s": round(elapsed, 1),
            "criterion": tc.criterion,
        })
    return results


def scorecard(results: list, label: str) -> dict:
    from collections import defaultdict
    tier_stats = defaultdict(lambda: {"verified": 0, "failed": 0, "unknown": 0, "total": 0})
    for r in results:
        s = tier_stats[r["tier"]]
        s[r["verdict"]] += 1
        s["total"] += 1

    print("\n" + "═" * 70)
    print(f" SECURITY PROFICIENCY — {label}")
    print("═" * 70)
    print(f"\n  {'Tier':<8} {'Verified':<10} {'Rate':<8} {'Failed':<8} {'Unknown'}")
    print(f"  {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")
    tv = tf = tu = tn = 0
    for tier, s in sorted(tier_stats.items()):
        denom = s["verified"] + s["failed"]
        rate = f"{100*s['verified']//denom}%" if denom else "n/a"
        print(f"  {tier:<8} {s['verified']:<10} {rate:<8} {s['failed']:<8} {s['unknown']}")
        tv += s["verified"]; tf += s["failed"]; tu += s["unknown"]; tn += s["total"]

    denom = tv + tf
    rate = 100 * tv // denom if denom else 0
    print(f"  {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")
    print(f"  {'OVERALL':<8} {tv}/{tn:<8} {(str(rate)+'%'):<8} {tf:<8} {tu}")
    return {"verified": tv, "failed": tf, "unknown": tu, "total": tn, "rate": rate,
            "by_tier": {k: dict(v) for k, v in tier_stats.items()}}


def main():
    args = sys.argv[1:]
    high = "--high" in args
    expert = "--expert" in args
    quick = "--quick" in args
    live = "--live-recon" in args
    no_learn = "--no-learn" in args
    rounds = 1
    if "--rounds" in args:
        try:
            rounds = max(1, int(args[args.index("--rounds") + 1]))
        except Exception:
            rounds = 1
    global FORCE_MODEL
    if "--model" in args:
        try:
            FORCE_MODEL = args[args.index("--model") + 1]
        except Exception:
            FORCE_MODEL = ""

    battery = list(MID_BATTERY)
    if high or expert:
        battery += HIGH_BATTERY
    if expert:
        battery += EXPERT_BATTERY
    if quick:
        battery = MID_BATTERY[:4] + (HIGH_BATTERY[:2] if (high or expert) else [])
    if live:
        battery += LIVE_RECON_BATTERY

    tier_label = ("MID"
                  + (" + HIGH" if (high or expert) else "")
                  + (" + EXPERT" if expert else "")
                  + (" + LIVE-RECON" if live else ""))
    print("═" * 70)
    print(" JARVIS SECURITY PROFICIENCY HARNESS  (the sandbox)")
    print(f" Battery: {tier_label}   |   Tasks/round: {len(battery)}   |   Rounds: {rounds}")
    print(" Verified by objective criteria — NOT the model's self-report")
    print(" Self-learning: failures logged to training/learning_log.jsonl")
    print("═" * 70)

    # Backend up?
    try:
        urllib.request.urlopen(f"{BACKEND}/api/status", timeout=5)
    except Exception:
        print("\n❌ Backend not running. Start it:  python web_main.py")
        return

    all_rounds = []
    for rnd in range(1, rounds + 1):
        results = run_round(battery, rnd, learn=(not no_learn))
        sc = scorecard(results, f"ROUND {rnd}/{rounds}  ({tier_label})")
        all_rounds.append({"round": rnd, "score": sc, "results": results})

    # ── Trend across rounds ──────────────────────────────────────────────
    print("\n" + "═" * 70)
    print(" HONEST READ")
    print("═" * 70)
    rates = [r["score"]["rate"] for r in all_rounds]
    if rounds > 1:
        print(f"\n  Per-round verified rate: {' → '.join(str(x)+'%' for x in rates)}")
        spread = max(rates) - min(rates)
        print(f"  Consistency spread: {spread} points "
              f"({'stable' if spread <= 10 else 'variable — local model is non-deterministic'})")

    final = all_rounds[-1]["score"]
    pct = final["rate"]
    print()
    if pct >= 85:
        print(f"  {pct}% verified — strong analyst-level reasoning on these tasks.")
    elif pct >= 65:
        print(f"  {pct}% verified — solid mid-level; {final['failed']} real gaps to close.")
    elif pct >= 40:
        print(f"  {pct}% verified — partial; usable as an assistant, not a lead analyst.")
    else:
        print(f"  {pct}% verified — below analyst bar on these tasks. Local-model ceiling.")
    print(f"  ❓ {final['unknown']} unknown (backend/tool error — NOT counted as success).")
    print("\n  Ceiling note: this measures RECON/TRIAGE/ANALYSIS/REMEDIATION reasoning.")
    print("  It does NOT test autonomous exploitation — that stays human-driven.")
    if not no_learn:
        fails = sum(r["score"]["failed"] for r in all_rounds)
        print(f"  🧠 {fails} failure-lessons written to the learning corpus for review.")

    # ── Save ─────────────────────────────────────────────────────────────
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "battery": tier_label, "rounds": rounds,
        "final_rate": pct, "rate_trend": rates,
        "rounds_detail": all_rounds,
    }
    out = ROOT / "training" / "security_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Report saved: {out}")


if __name__ == "__main__":
    main()
