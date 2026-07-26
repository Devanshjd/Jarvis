"""
J.A.R.V.I.S -- Earn Loop Plugin
Automaton-inspired money engine with the owner in the loop: JARVIS proposes
ideas, tracks costs/revenue in INR, and recommends kills -- the owner decides.

Commands:
    /earn                       -- P&L status + recommendations
    /earn ideas [context]       -- propose new money-making ideas
    /earn add <title>           -- add your own idea
    /earn approve <id>          -- proposed -> testing (max 3 in parallel)
    /earn promote <id>          -- testing -> active (it's earning!)
    /earn kill <id> [reason]    -- kill a loser
    /earn park <id>             -- shelve for later
    /earn cost <id> <amt> [note]    -- log money spent (INR)
    /earn revenue <id> <amt> [note] -- log money earned (INR)
    /earn review                -- run the kill-rule review
"""

from core.plugin_manager import PluginBase
from core.earn_loop import EarnLoop
from core.bug_bounty import get_tracker

HELP = __doc__.split("Commands:")[1].rstrip()

BOUNTY_HELP = """
    /bounty                          -- targets + earnings status
    /bounty add <program> [platform] -- track a program (hackerone/bugcrowd/...)
    /bounty scope <id> in|out <asset> -- record in/out-of-scope assets
    /bounty check <id> <asset>       -- is an asset in scope? (safety check)
    /bounty recon <id>               -- generate a recon methodology checklist
    /bounty report <id> [type] <title> -- draft a CVSS+CWE report (type: idor/ssrf/cors/...)
    /bounty submit <id> <sev> <title> -- log a submission
    /bounty reward <id> <amt> <title> -- log a payout (INR)
    /bounty status <id> <status>     -- recon|testing|reporting|parked|done
    /bounty tools                    -- check which recon tools are installed
    /bounty scan <id> <root-domain>  -- run the scope-gated recon pipeline (local)
    /bounty hunt <id> <root-domain>  -- deep hunt: auto-findings + manual hit-list
"""


class EarnLoopPlugin(PluginBase):
    name = "earn_loop"
    description = "Earn loop -- idea engine: propose, test, measure, kill losers"
    version = "1.0"

    def __init__(self, jarvis):
        super().__init__(jarvis)
        self.loop = EarnLoop(jarvis)
        self.bounty = get_tracker(jarvis)

    def activate(self):
        n = len(self.loop.ideas)
        print(f"[JARVIS] Earn loop: {n} idea(s) in the ledger")

    def get_status(self) -> dict:
        ideas = self.loop.ideas.values()
        return {
            "name": self.name,
            "active": True,
            "ideas": len(self.loop.ideas),
            "testing": sum(1 for i in ideas if i.status == "testing"),
            "net_inr": sum(i.profit for i in ideas),
        }

    # ══════════════════════════════════════════════════════════════
    # COMMANDS
    # ══════════════════════════════════════════════════════════════

    def on_command(self, command: str, args: str) -> bool:
        if command == "earn":
            try:
                self._reply(self._dispatch(args.strip()))
            except (KeyError, ValueError, RuntimeError) as e:
                self._reply(f"Earn loop: {e}")
            return True
        if command == "bounty":
            try:
                self._reply(self._dispatch_bounty(args.strip()))
            except (KeyError, ValueError, RuntimeError) as e:
                self._reply(f"Bounty: {e}")
            return True
        return False

    def _dispatch(self, args: str) -> str:
        if not args or args == "status":
            return self.loop.status_report()

        sub, _, rest = args.partition(" ")
        rest = rest.strip()

        if sub == "ideas":
            ideas = self.loop.propose_ideas(context=rest)
            if not ideas:
                return "No new ideas generated -- ledger already has the seed set."
            out = ["Proposed (approve the ones you like -- /earn approve <id>):", ""]
            for i in ideas:
                out.append(f"  [{i.id}] {i.title}  ({i.channel})")
                if i.next_action:
                    out.append(f"      first step: {i.next_action}")
            return "\n".join(out)

        if sub == "add":
            if not rest:
                return "Usage: /earn add <title>"
            i = self.loop.add_idea(rest)
            return f"Added [{i.id}] {i.title} -- approve with /earn approve {i.id}"

        if sub in ("approve", "promote", "kill", "park"):
            idea_id, _, reason = rest.partition(" ")
            if not idea_id:
                return f"Usage: /earn {sub} <id>"
            if sub == "approve":
                i = self.loop.approve(idea_id)
                return f"[{i.id}] {i.title} -> TESTING. First step: {i.next_action or 'define it!'}"
            if sub == "promote":
                i = self.loop.promote(idea_id)
                return f"[{i.id}] {i.title} -> ACTIVE. It earned its place."
            if sub == "kill":
                i = self.loop.kill(idea_id, reason.strip())
                return f"[{i.id}] {i.title} -> KILLED ({i.kill_reason}). On to the next."
            i = self.loop.park(idea_id)
            return f"[{i.id}] {i.title} -> PARKED."

        if sub in ("cost", "revenue"):
            parts = rest.split(" ", 2)
            if len(parts) < 2:
                return f"Usage: /earn {sub} <id> <amount> [note]"
            idea_id, amount = parts[0], parts[1]
            note = parts[2] if len(parts) > 2 else ""
            try:
                value = float(amount.replace("₹", "").replace(",", ""))
            except ValueError:
                return f"'{amount}' is not a number."
            log = self.loop.log_cost if sub == "cost" else self.loop.log_revenue
            i = log(idea_id, value, note)
            return (f"[{i.id}] {sub} ₹{value:.0f} logged. "
                    f"Net now ₹{i.profit:+.0f}.")

        if sub == "review":
            recs = self.loop.review_cycle()
            if not recs:
                return "Review: nothing to flag. Keep executing."
            out = ["Review recommendations (your call):"]
            out += [f"  {r['action'].upper()} {r['idea_id']} -- {r['reason']}" for r in recs]
            return "\n".join(out)

        if sub == "help":
            return "Earn loop commands:" + HELP

        return f"Unknown subcommand '{sub}'. Try /earn help"

    def _dispatch_bounty(self, args: str) -> str:
        if not args or args == "status":
            return self.bounty.status_report()

        sub, _, rest = args.partition(" ")
        rest = rest.strip()

        if sub == "help":
            return "Bug-bounty commands:" + BOUNTY_HELP

        if sub == "add":
            if not rest:
                return "Usage: /bounty add <program> [platform]"
            program, _, platform = rest.partition(" ")
            # allow multi-word program in quotes
            if rest.startswith(('"', "'")):
                q = rest[0]
                program, _, platform = rest[1:].partition(q)
                platform = platform.strip()
            t = self.bounty.add_target(program.strip() or rest, (platform or "other").strip())
            return (f"Tracking [{t.id}] {t.program} ({t.platform}). "
                    f"Add scope: /bounty scope {t.id} in <asset>")

        if sub == "scope":
            parts = rest.split(" ", 2)
            if len(parts) < 3 or parts[1] not in ("in", "out"):
                return "Usage: /bounty scope <id> in|out <asset>"
            tid, side, asset = parts[0], parts[1], parts[2].strip()
            t = self.bounty.get(tid)
            (t.scope_in if side == "in" else t.scope_out).append(asset)
            self.bounty._save()
            return f"[{t.id}] {side}-scope += {asset}"

        if sub == "check":
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                return "Usage: /bounty check <id> <asset>"
            verdict = self.bounty.in_scope(parts[0], parts[1].strip())
            if verdict is True:
                return f"✅ {parts[1].strip()} appears IN scope. Still confirm against the policy."
            if verdict is False:
                return f"⛔ {parts[1].strip()} is OUT of scope — do NOT test it."
            return f"❓ {parts[1].strip()} isn't in your recorded scope. Verify on the program page before testing."

        if sub == "recon":
            if not rest:
                return "Usage: /bounty recon <id>"
            steps = self.bounty.recon_checklist(rest)
            out = [f"Recon checklist for [{rest}] (methodology — stay in scope):", ""]
            out += [f"  {i}. {s}" for i, s in enumerate(steps, 1)]
            return "\n".join(out)

        if sub == "report":
            parts = rest.split(" ", 2)
            if len(parts) < 2:
                return ("Usage: /bounty report <id> [bug-type] <title>\n"
                        "  bug-type (optional) auto-fills CVSS + CWE + remediation:\n"
                        "    idor · access-control · ssrf · open-redirect · cors ·\n"
                        "    info-disclosure · subdomain-takeover · xss-reflected ·\n"
                        "    xss-stored · sqli · auth-bypass\n"
                        "  e.g. /bounty report ab12 idor Access any user's invoice via id param")
            self.bounty.get(parts[0])  # validate id
            from core import cvss
            # If the 2nd token is a known bug-type, use it; else it's the title.
            if len(parts) == 3 and parts[1].strip().lower().replace(" ", "-") in cvss.BUG_TYPES:
                btype, title = parts[1].strip(), parts[2].strip()
            else:
                btype, title = "", rest.split(" ", 1)[1].strip()
            draft = self.bounty.draft_report(title=title, bug_type=btype)
            return (f"Draft report for [{parts[0]}] — fill in the PoC and VERIFY "
                    f"before submitting:\n\n{draft}")

        if sub == "submit":
            parts = rest.split(" ", 2)
            if len(parts) < 3:
                return "Usage: /bounty submit <id> <severity> <title>"
            t = self.bounty.log_submission(parts[0], parts[2].strip(), severity=parts[1])
            return f"[{t.id}] submission logged ({len(t.submissions)} total). Good luck on triage."

        if sub == "reward":
            parts = rest.split(" ", 2)
            if len(parts) < 3:
                return "Usage: /bounty reward <id> <amount> <title>"
            try:
                amt = float(parts[1].replace("₹", "").replace(",", ""))
            except ValueError:
                return f"'{parts[1]}' is not a number."
            t = self.bounty.log_submission(parts[0], parts[2].strip(), status="resolved", reward_inr=amt)
            return f"💰 [{t.id}] payout ₹{amt:.0f} logged for '{parts[2].strip()}'. Nice."

        if sub == "status":
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                return "Usage: /bounty status <id> <recon|testing|reporting|parked|done>"
            t = self.bounty.set_status(parts[0], parts[1].strip())
            return f"[{t.id}] {t.program} -> {t.status.upper()}"

        if sub == "tools":
            from core.recon_pipeline import tools_report
            return tools_report()

        if sub == "scan":
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                return "Usage: /bounty scan <id> <root-domain>"
            from core.recon_pipeline import get_pipeline
            return get_pipeline(self.jarvis).run(parts[0], parts[1].strip())

        if sub == "hunt":
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                return "Usage: /bounty hunt <id> <root-domain>"
            from core.vuln_hunter import get_hunter
            return get_hunter(self.jarvis).hunt(parts[0], parts[1].strip())

        return f"Unknown bounty subcommand '{sub}'. Try /bounty help"

    def _reply(self, text: str):
        try:
            self.jarvis.chat.add_message("assistant", text)
        except Exception:
            print(text)
