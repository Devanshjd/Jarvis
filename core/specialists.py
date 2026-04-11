"""
J.A.R.V.I.S -- Multi-Specialist System
Instead of one general AI, JARVIS has a TEAM of internal specialists.

The thinking engine auto-selects the right specialist based on context.
Each specialist has its own:
    - Identity / system prompt addition
    - Trigger patterns (regex)
    - Preferred tools
    - Domain-specific reasoning rules
    - Knowledge domains

Integration points:
    - select_specialist() consumes LocalNLP.understand() output (ParsedInput)
    - The selected specialist's identity_prompt is injected into the system prompt
    - The specialist's reasoning_rules feed into DeductiveReasoner
    - The specialist's preferred_tools influence tool selection in the orchestrator

Dependencies: standard library only.
Thread-safe: all mutable state is protected by locks.
"""

import re
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("jarvis.specialists")


# ═════════════════════════════════════════════════════════════════
#  DATA STRUCTURE
# ═════════════════════════════════════════════════════════════════

@dataclass
class Specialist:
    """A domain specialist within JARVIS's cognitive team."""
    name: str                           # e.g. "Security Auditor"
    role: str                           # short description
    identity_prompt: str                # system prompt addition when active
    trigger_patterns: list              # regex patterns that activate this specialist
    preferred_tools: list               # tools this specialist likes to use
    reasoning_rules: list               # deduction rules specific to this domain
    knowledge_domains: list             # what topics this specialist knows about
    confidence_boost: float = 0.15      # how much to boost confidence when matched

    # Compiled patterns cached on first use
    _compiled: list = field(default_factory=list, repr=False, compare=False)

    def _ensure_compiled(self):
        if not self._compiled and self.trigger_patterns:
            self._compiled = [
                re.compile(p, re.IGNORECASE) for p in self.trigger_patterns
            ]

    def match_score(self, text: str) -> float:
        """Return 0.0-1.0 indicating how strongly this text activates the specialist."""
        self._ensure_compiled()
        if not self._compiled:
            return 0.0
        hits = sum(1 for pat in self._compiled if pat.search(text))
        return min(hits / max(len(self._compiled) * 0.3, 1), 1.0)


# ═════════════════════════════════════════════════════════════════
#  SPECIALIST TEAM
# ═════════════════════════════════════════════════════════════════

class SpecialistTeam:
    """
    Manages the roster of internal specialists and selects the best one
    for any given input context.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._specialists: dict[str, Specialist] = {}
        self._selection_history: list[dict] = []  # track selections for learning
        self._register_builtins()
        logger.info(
            "SpecialistTeam initialized with %d specialists", len(self._specialists)
        )

    # ── Public API ──────────────────────────────────────────────

    def select_specialist(
        self,
        text: str,
        entities: Optional[dict] = None,
        topic: str = "",
        intent: str = "",
    ) -> Specialist:
        """
        Auto-pick the best specialist for the given input.

        Args:
            text:     Raw user input text.
            entities: Extracted entities from LocalNLP (e.g. {"domain": [...], "cve": [...]}).
            topic:    Detected topic string.
            intent:   Detected intent (ask, command, inform, etc.).

        Returns:
            The best-matching Specialist. Falls back to the Generalist if no
            strong match is found.
        """
        entities = entities or {}

        # Build a combined scoring string from all available signals
        scoring_text = f"{text} {topic} {intent} {' '.join(_flatten_entities(entities))}"

        best_score = 0.0
        best_specialist = None

        with self._lock:
            for spec in self._specialists.values():
                score = spec.match_score(scoring_text)

                # Bonus for entity-type alignment
                score += self._entity_bonus(spec, entities)

                # Bonus for intent alignment
                score += self._intent_bonus(spec, intent)

                if score > best_score:
                    best_score = score
                    best_specialist = spec

        # Fall back to Generalist if no specialist scored meaningfully
        if best_specialist is None or best_score < 0.15:
            best_specialist = self._specialists.get(
                "Generalist", self._make_generalist()
            )

        # Record selection for future learning
        self._selection_history.append({
            "text_snippet": text[:80],
            "selected": best_specialist.name,
            "score": round(best_score, 3),
        })
        if len(self._selection_history) > 500:
            self._selection_history = self._selection_history[-250:]

        logger.debug(
            "Selected specialist: %s (score=%.3f) for: %.60s",
            best_specialist.name, best_score, text,
        )
        return best_specialist

    def get_specialist(self, name: str) -> Optional[Specialist]:
        """Get a specialist by exact name."""
        with self._lock:
            return self._specialists.get(name)

    def get_prompt_injection(self, specialist: Specialist) -> str:
        """Return the system prompt addition for this specialist."""
        header = f"\n[Active Specialist: {specialist.name} -- {specialist.role}]\n"
        return header + specialist.identity_prompt

    def get_reasoning_rules(self, specialist: Specialist) -> list:
        """Return deduction rules for this specialist (condition, conclusion, name, confidence)."""
        return list(specialist.reasoning_rules)

    def list_specialists(self) -> list[Specialist]:
        """Return all registered specialists."""
        with self._lock:
            return list(self._specialists.values())

    def add_specialist(self, specialist: Specialist):
        """Dynamically add (or replace) a specialist. Used for self-evolution."""
        with self._lock:
            self._specialists[specialist.name] = specialist
        logger.info("Added specialist: %s", specialist.name)

    def remove_specialist(self, name: str) -> bool:
        """Remove a specialist by name. Returns True if removed."""
        with self._lock:
            if name in self._specialists and name != "Generalist":
                del self._specialists[name]
                logger.info("Removed specialist: %s", name)
                return True
        return False

    # ── Scoring helpers ─────────────────────────────────────────

    @staticmethod
    def _entity_bonus(spec: Specialist, entities: dict) -> float:
        """Give bonus points when extracted entity types align with specialist domains."""
        bonus = 0.0
        entity_domain_map = {
            "cve": ["cybersecurity", "vulnerability"],
            "ip": ["networking", "cybersecurity"],
            "ip_cidr": ["networking"],
            "domain": ["networking", "cybersecurity", "web"],
            "port": ["networking", "cybersecurity"],
            "file_path": ["debugging", "system administration"],
            "url": ["web", "research"],
            "email": ["communication"],
        }
        for etype, domains in entity_domain_map.items():
            if entities.get(etype):
                if any(d in spec.knowledge_domains for d in domains):
                    bonus += 0.15
        return min(bonus, 0.3)

    @staticmethod
    def _intent_bonus(spec: Specialist, intent: str) -> float:
        """Give bonus for intent alignment."""
        intent_map = {
            "Security Auditor": ["command", "ask"],
            "Debugger": ["ask", "inform"],
            "Code Reviewer": ["command", "ask"],
            "System Architect": ["ask", "command"],
            "Research Analyst": ["ask"],
            "DevOps Engineer": ["command", "ask"],
            "Data Analyst": ["command", "ask"],
            "Network Specialist": ["command", "ask"],
            "Prompt Engineer": ["command", "ask"],
            "Task Planner": ["command", "ask"],
        }
        if intent in intent_map.get(spec.name, []):
            return 0.05
        return 0.0

    # ── Built-in roster ─────────────────────────────────────────

    def _register_builtins(self):
        """Register the full roster of built-in specialists."""
        builtins = [
            self._make_security_auditor(),
            self._make_debugger(),
            self._make_code_reviewer(),
            self._make_system_architect(),
            self._make_research_analyst(),
            self._make_devops_engineer(),
            self._make_data_analyst(),
            self._make_network_specialist(),
            self._make_prompt_engineer(),
            self._make_task_planner(),
            self._make_generalist(),
        ]
        for spec in builtins:
            self._specialists[spec.name] = spec

    # ─────────────────────────────────────────────────────────────
    #  SPECIALIST DEFINITIONS
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _make_security_auditor() -> Specialist:
        return Specialist(
            name="Security Auditor",
            role="Penetration tester and security analyst",
            identity_prompt=(
                "You are an expert penetration tester and security auditor.\n"
                "Think in attack chains: reconnaissance -> enumeration -> vulnerability analysis -> exploitation -> post-exploitation.\n"
                "Always consider the OWASP Top 10 for web applications.\n"
                "Reference the MITRE ATT&CK framework when discussing attack techniques.\n"
                "Think about what an attacker would do at every step.\n"
                "Prioritize findings by severity: Critical > High > Medium > Low > Informational.\n"
                "Always suggest remediations alongside findings.\n"
                "Be thorough: check service versions, default credentials, misconfigurations, and known CVEs."
            ),
            trigger_patterns=[
                r"\bvulnerab\w*\b",
                r"\bexploit\w*\b",
                r"\bCVE-\d{4}-\d+\b",
                r"\bpentest\w*\b",
                r"\bhack\w*\b",
                r"\bsecurity\b",
                r"\baudit\b",
                r"\bOWASP\b",
                r"\binjection\b",
                r"\bXSS\b",
                r"\bsql\s*inject\w*\b",
                r"\bbuffer\s*overflow\b",
                r"\bprivilege\s*escalat\w*\b",
                r"\breverse\s*shell\b",
                r"\bMITRE\b",
                r"\bATT&CK\b",
                r"\bnmap\b",
                r"\brecon\w*\b",
                r"\bbrute\s*force\b",
                r"\bmalware\b",
                r"\bransomware\b",
                r"\bphishing\b",
            ],
            preferred_tools=[
                "port_scan", "net_scan", "cve_search", "exploit_search",
                "wifi_scan", "web_search", "run_command", "scan_screen",
            ],
            reasoning_rules=[
                {
                    "name": "sec_open_port_version_check",
                    "condition": "open port detected",
                    "conclusion": "Enumerate the service version on this port and check for known CVEs.",
                    "confidence": 0.9,
                },
                {
                    "name": "sec_web_server_headers",
                    "condition": "web server detected (port 80/443/8080/8443)",
                    "conclusion": "Check HTTP security headers: HSTS, CSP, X-Frame-Options, X-Content-Type-Options.",
                    "confidence": 0.9,
                },
                {
                    "name": "sec_vuln_exploitability",
                    "condition": "vulnerability found",
                    "conclusion": "Determine if this vulnerability is exploitable in the current context. Check for public exploits.",
                    "confidence": 0.85,
                },
                {
                    "name": "sec_subdomain_enumerate",
                    "condition": "subdomain discovered",
                    "conclusion": "Enumerate further: check for additional subdomains, resolve IPs, scan for services.",
                    "confidence": 0.8,
                },
                {
                    "name": "sec_default_creds",
                    "condition": "service with authentication detected",
                    "conclusion": "Check for default or weak credentials before attempting advanced attacks.",
                    "confidence": 0.85,
                },
            ],
            knowledge_domains=[
                "cybersecurity", "penetration testing", "vulnerability", "networking",
                "web security", "cryptography", "malware analysis", "forensics",
            ],
            confidence_boost=0.2,
        )

    @staticmethod
    def _make_debugger() -> Specialist:
        return Specialist(
            name="Debugger",
            role="Systematic error detective and bug hunter",
            identity_prompt=(
                "You are a systematic debugger and error detective.\n"
                "Read error messages carefully -- the answer is almost always in the traceback.\n"
                "Trace the root cause, never just treat symptoms.\n"
                "Check logs, reproduce issues, verify assumptions.\n"
                "Never guess -- investigate. Form a hypothesis, then test it.\n"
                "Common pattern: read the error -> identify the failing line -> check inputs to that line -> find the mismatch.\n"
                "Always suggest a concrete fix, not just a diagnosis."
            ),
            trigger_patterns=[
                r"\berror\b",
                r"\bbug\b",
                r"\bcrash\w*\b",
                r"\btraceback\b",
                r"\bexception\b",
                r"\bnot\s+working\b",
                r"\bbroken\b",
                r"\bfix\b",
                r"\bdebug\w*\b",
                r"\bfail\w*\b",
                r"\bsegfault\b",
                r"\bcore\s*dump\b",
                r"\bstack\s*trace\b",
                r"\bundefined\b",
                r"\bNull\w*\b",
                r"\bTypeError\b",
                r"\bValueError\b",
                r"\bKeyError\b",
                r"\bAttributeError\b",
                r"\bImportError\b",
                r"\bSyntaxError\b",
                r"\bRuntimeError\b",
            ],
            preferred_tools=[
                "run_python", "run_command", "scan_screen", "save_file",
            ],
            reasoning_rules=[
                {
                    "name": "dbg_traceback_analysis",
                    "condition": "traceback or stack trace present",
                    "conclusion": "Identify the actual error line (bottom of traceback) and the exception type. Work upward to find root cause.",
                    "confidence": 0.95,
                },
                {
                    "name": "dbg_import_error",
                    "condition": "ImportError or ModuleNotFoundError",
                    "conclusion": "Check if the package is installed (pip list), check for typos in module name, verify virtual environment.",
                    "confidence": 0.9,
                },
                {
                    "name": "dbg_timeout",
                    "condition": "timeout or connection refused",
                    "conclusion": "Check if the target service is running, verify network connectivity, check firewall rules, verify port.",
                    "confidence": 0.85,
                },
                {
                    "name": "dbg_permission_denied",
                    "condition": "PermissionError or Access Denied",
                    "conclusion": "Check file/directory permissions, verify the running user, check if admin/root is needed.",
                    "confidence": 0.9,
                },
                {
                    "name": "dbg_type_mismatch",
                    "condition": "TypeError detected",
                    "conclusion": "Check the types of all arguments at the error line. Look for None where an object is expected, or string where int is needed.",
                    "confidence": 0.85,
                },
            ],
            knowledge_domains=[
                "debugging", "error analysis", "logging", "testing",
                "python", "system administration",
            ],
            confidence_boost=0.15,
        )

    @staticmethod
    def _make_code_reviewer() -> Specialist:
        return Specialist(
            name="Code Reviewer",
            role="Senior code reviewer focused on quality and security",
            identity_prompt=(
                "You are a senior code reviewer with deep experience.\n"
                "Check for: security vulnerabilities, performance issues, code smells, SOLID principle violations, error handling gaps.\n"
                "Give actionable feedback -- not just 'this is bad' but 'change X to Y because Z'.\n"
                "Prioritize issues: security > correctness > performance > readability > style.\n"
                "Look for: hardcoded secrets, SQL injection, XSS, missing input validation, race conditions, resource leaks.\n"
                "Acknowledge good code too -- positive reinforcement matters."
            ),
            trigger_patterns=[
                r"\breview\b",
                r"\bcode\s*quality\b",
                r"\brefactor\w*\b",
                r"\bclean\s*up\b",
                r"\bimprove\s*code\b",
                r"\bbest\s*practices?\b",
                r"\bcode\s*smell\b",
                r"\bSOLID\b",
                r"\blint\w*\b",
                r"\btech\s*debt\b",
                r"\banti.?pattern\b",
                r"\bDRY\b",
                r"\bKISS\b",
            ],
            preferred_tools=[
                "run_python", "save_file", "git_command", "modify_file",
            ],
            reasoning_rules=[
                {
                    "name": "cr_no_error_handling",
                    "condition": "code block with no try/except or error handling",
                    "conclusion": "Suggest adding appropriate error handling. Identify which exceptions could occur and how to handle them.",
                    "confidence": 0.85,
                },
                {
                    "name": "cr_hardcoded_credentials",
                    "condition": "hardcoded password, API key, token, or secret in code",
                    "conclusion": "CRITICAL: Flag immediately. Suggest using environment variables or a secrets manager.",
                    "confidence": 0.95,
                },
                {
                    "name": "cr_sql_injection",
                    "condition": "SQL query built with string concatenation or f-strings",
                    "conclusion": "SQL INJECTION RISK: Suggest using parameterized queries or an ORM.",
                    "confidence": 0.95,
                },
                {
                    "name": "cr_no_input_validation",
                    "condition": "function accepts user input without validation",
                    "conclusion": "Suggest adding input validation: type checks, length limits, allowed values, sanitization.",
                    "confidence": 0.85,
                },
                {
                    "name": "cr_duplicate_code",
                    "condition": "similar code blocks repeated",
                    "conclusion": "DRY violation: extract into a shared function or class method.",
                    "confidence": 0.8,
                },
            ],
            knowledge_domains=[
                "code quality", "software engineering", "security", "design patterns",
                "python", "testing", "refactoring",
            ],
            confidence_boost=0.15,
        )

    @staticmethod
    def _make_system_architect() -> Specialist:
        return Specialist(
            name="System Architect",
            role="Senior system architect for scalable design",
            identity_prompt=(
                "You are a senior system architect.\n"
                "Think about: scalability, maintainability, separation of concerns, loose coupling, high cohesion.\n"
                "Consider trade-offs explicitly: consistency vs availability, complexity vs flexibility, speed vs correctness.\n"
                "Design for the future but build for today -- avoid over-engineering.\n"
                "Use diagrams (describe them textually) when explaining architecture.\n"
                "Always consider: what happens when this component fails? What if load increases 10x?"
            ),
            trigger_patterns=[
                r"\barchitect\w*\b",
                r"\bdesign\s*(?:pattern|system|api|database|schema)\b",
                r"\bscalab\w*\b",
                r"\bmicroservices?\b",
                r"\bmonolith\b",
                r"\bAPI\s*design\b",
                r"\bdatabase\s*(?:design|schema|model)\b",
                r"\bsystem\s*design\b",
                r"\binfrastructure\b",
                r"\bevent.?driven\b",
                r"\bmessage\s*queue\b",
                r"\bload\s*balanc\w*\b",
                r"\bcaching\b",
            ],
            preferred_tools=[
                "save_file", "run_python", "web_search",
            ],
            reasoning_rules=[
                {
                    "name": "arch_monolith_growth",
                    "condition": "monolithic application growing in complexity",
                    "conclusion": "Consider extracting bounded contexts into separate services. Identify natural seams in the codebase.",
                    "confidence": 0.8,
                },
                {
                    "name": "arch_shared_state",
                    "condition": "multiple components sharing mutable state",
                    "conclusion": "Suggest a message queue or event bus to decouple components. Consider CQRS for read/write separation.",
                    "confidence": 0.85,
                },
                {
                    "name": "arch_repeated_code",
                    "condition": "repeated logic across services or modules",
                    "conclusion": "Extract into a shared library or introduce an abstraction layer.",
                    "confidence": 0.8,
                },
                {
                    "name": "arch_single_point_failure",
                    "condition": "critical path with no redundancy",
                    "conclusion": "Single point of failure detected. Consider replication, failover, or circuit breaker pattern.",
                    "confidence": 0.9,
                },
            ],
            knowledge_domains=[
                "system design", "software architecture", "distributed systems",
                "databases", "API design", "cloud computing", "design patterns",
            ],
            confidence_boost=0.15,
        )

    @staticmethod
    def _make_research_analyst() -> Specialist:
        return Specialist(
            name="Research Analyst",
            role="Deep researcher with multi-source analysis",
            identity_prompt=(
                "You are a deep research analyst.\n"
                "Gather information from multiple sources, cross-reference claims, and identify patterns.\n"
                "Always note the date and reliability of your sources.\n"
                "Distinguish between facts, opinions, and speculation.\n"
                "Provide comprehensive analysis with nuance -- avoid oversimplification.\n"
                "When information is uncertain or contradictory, say so explicitly.\n"
                "Structure findings: Executive Summary -> Key Findings -> Detailed Analysis -> Sources."
            ),
            trigger_patterns=[
                r"\bresearch\b",
                r"\binvestigat\w*\b",
                r"\bfind\s*out\b",
                r"\bcompar\w*\b",
                r"\banalyz\w*\b",
                r"\bstudy\b",
                r"\blearn\s*about\b",
                r"\bwhat\s*is\b",
                r"\bexplain\b",
                r"\bhistory\s*of\b",
                r"\bpros\s*and\s*cons\b",
                r"\bdifference\s*between\b",
                r"\bhow\s*does\b",
            ],
            preferred_tools=[
                "web_search", "get_wiki", "get_news", "run_python",
            ],
            reasoning_rules=[
                {
                    "name": "res_single_source",
                    "condition": "only one source for a claim",
                    "conclusion": "Need more sources to verify. Cross-reference with at least 2 additional sources.",
                    "confidence": 0.7,
                },
                {
                    "name": "res_contradicting_info",
                    "condition": "multiple sources contradict each other",
                    "conclusion": "Flag the uncertainty explicitly. Present both viewpoints and note which sources are more authoritative.",
                    "confidence": 0.8,
                },
                {
                    "name": "res_outdated_info",
                    "condition": "information is more than 2 years old",
                    "conclusion": "Note the date prominently. Search for more recent information to see if the situation has changed.",
                    "confidence": 0.75,
                },
                {
                    "name": "res_bias_detection",
                    "condition": "source has commercial or political interest in the claim",
                    "conclusion": "Flag potential bias. Seek independent or academic sources for verification.",
                    "confidence": 0.7,
                },
            ],
            knowledge_domains=[
                "research", "analysis", "fact-checking", "academia",
                "current events", "technology trends",
            ],
            confidence_boost=0.1,
        )

    @staticmethod
    def _make_devops_engineer() -> Specialist:
        return Specialist(
            name="DevOps Engineer",
            role="Infrastructure, CI/CD, and deployment expert",
            identity_prompt=(
                "You are a senior DevOps engineer.\n"
                "Think about: infrastructure as code, containerization, CI/CD pipelines, monitoring, scaling, reliability.\n"
                "Automate everything that is done more than twice.\n"
                "Consider: What happens when this fails at 3 AM? Is there monitoring? Alerting? Auto-recovery?\n"
                "Prefer declarative configuration over imperative scripts.\n"
                "Security in DevOps: least privilege, secrets management, image scanning, signed artifacts."
            ),
            trigger_patterns=[
                r"\bdeploy\w*\b",
                r"\bCI/?CD\b",
                r"\bdocker\w*\b",
                r"\bkubernetes\b",
                r"\bk8s\b",
                r"\bserver\b",
                r"\bcloud\b",
                r"\bAWS\b",
                r"\bAzure\b",
                r"\bGCP\b",
                r"\bpipeline\b",
                r"\bcontainer\w*\b",
                r"\bterraform\b",
                r"\bansible\b",
                r"\bnginx\b",
                r"\bjenkins\b",
                r"\bgithub\s*actions?\b",
                r"\bhelm\b",
                r"\binfrastructure\b",
            ],
            preferred_tools=[
                "run_command", "git_command", "save_file", "run_python",
            ],
            reasoning_rules=[
                {
                    "name": "devops_manual_deploy",
                    "condition": "manual deployment process described",
                    "conclusion": "Suggest automating with CI/CD pipeline. Identify steps that can be scripted.",
                    "confidence": 0.85,
                },
                {
                    "name": "devops_no_monitoring",
                    "condition": "service running without monitoring or alerting",
                    "conclusion": "Suggest adding health checks, metrics collection, log aggregation, and alerting.",
                    "confidence": 0.9,
                },
                {
                    "name": "devops_single_server",
                    "condition": "production running on a single server",
                    "conclusion": "Single point of failure. Consider redundancy, load balancing, or container orchestration.",
                    "confidence": 0.85,
                },
                {
                    "name": "devops_secrets_in_code",
                    "condition": "secrets or credentials in source code or config files",
                    "conclusion": "CRITICAL: Move to secrets manager (Vault, AWS Secrets Manager, environment variables). Never commit secrets.",
                    "confidence": 0.95,
                },
            ],
            knowledge_domains=[
                "devops", "cloud computing", "containers", "CI/CD",
                "infrastructure", "monitoring", "linux", "networking",
            ],
            confidence_boost=0.15,
        )

    @staticmethod
    def _make_data_analyst() -> Specialist:
        return Specialist(
            name="Data Analyst",
            role="Data scientist for analysis and visualization",
            identity_prompt=(
                "You are an expert data analyst and data scientist.\n"
                "Analyze datasets methodically: understand the shape, check for missing data, identify distributions.\n"
                "Find patterns, correlations, and anomalies.\n"
                "Create clear visualizations -- choose the right chart type for the data.\n"
                "Apply statistical reasoning: hypothesis testing, confidence intervals, significance.\n"
                "Always warn about: small sample sizes, survivorship bias, correlation vs causation, confounding variables.\n"
                "Use pandas, matplotlib, seaborn when writing analysis code."
            ),
            trigger_patterns=[
                r"\bdata\s*(?:analy|scien|set|frame)\w*\b",
                r"\bstatistic\w*\b",
                r"\bgraph\b",
                r"\bchart\b",
                r"\bCSV\b",
                r"\bdataset\b",
                r"\btrend\w*\b",
                r"\bvisuali[zs]\w*\b",
                r"\bcorrelat\w*\b",
                r"\bregression\b",
                r"\bhistogram\b",
                r"\boutlier\w*\b",
                r"\bmean\b.*\b(?:median|average)\b",
                r"\bpandas\b",
                r"\bmatplotlib\b",
                r"\bplot\b",
            ],
            preferred_tools=[
                "run_python", "save_file", "web_search",
            ],
            reasoning_rules=[
                {
                    "name": "data_small_sample",
                    "condition": "sample size is small (n < 30)",
                    "conclusion": "Warn about statistical significance. Use non-parametric tests or bootstrap methods.",
                    "confidence": 0.85,
                },
                {
                    "name": "data_correlation_causation",
                    "condition": "correlation found between variables",
                    "conclusion": "Correlation does not imply causation. Look for confounding variables and consider the causal mechanism.",
                    "confidence": 0.9,
                },
                {
                    "name": "data_missing_values",
                    "condition": "missing data in dataset",
                    "conclusion": "Handle appropriately: understand WHY data is missing (MCAR, MAR, MNAR). Choose imputation strategy or exclude with justification.",
                    "confidence": 0.85,
                },
                {
                    "name": "data_outlier_detected",
                    "condition": "outliers present in data",
                    "conclusion": "Investigate outliers before removing: are they errors, or genuine extreme values? Document the decision.",
                    "confidence": 0.8,
                },
            ],
            knowledge_domains=[
                "data analysis", "statistics", "visualization", "machine learning",
                "pandas", "python", "databases",
            ],
            confidence_boost=0.15,
        )

    @staticmethod
    def _make_network_specialist() -> Specialist:
        return Specialist(
            name="Network Specialist",
            role="Network engineer for infrastructure and security",
            identity_prompt=(
                "You are a senior network engineer.\n"
                "Understand the OSI model deeply -- diagnose at the right layer.\n"
                "Think about: packet flow, routing tables, firewall rules, DNS resolution, subnetting, NAT.\n"
                "For wireless: channel interference, WPA3 vs WPA2, rogue APs, deauth attacks.\n"
                "Always consider security: segmentation, ACLs, IDS/IPS, encrypted protocols.\n"
                "When troubleshooting: start from the bottom (physical/link) and work up, or start from the application and work down."
            ),
            trigger_patterns=[
                r"\bnetwork\w*\b",
                r"\bWi-?Fi\b",
                r"\bfirewall\b",
                r"\bDNS\b",
                r"\brout\w*\b",
                r"\bsubnet\w*\b",
                r"\bVLAN\b",
                r"\bpacket\b",
                r"\bTCP\b",
                r"\bUDP\b",
                r"\bIP\s*address\b",
                r"\bping\b",
                r"\btraceroute\b",
                r"\blatency\b",
                r"\bbandwidth\b",
                r"\bVPN\b",
                r"\bNAT\b",
                r"\bDHCP\b",
                r"\bOSI\b",
                r"\bswitch\b.*\bport\b",
                r"\bwireless\b",
            ],
            preferred_tools=[
                "port_scan", "net_scan", "wifi_scan", "network_info",
                "run_command", "web_search",
            ],
            reasoning_rules=[
                {
                    "name": "net_open_mgmt_port",
                    "condition": "management port open (SSH, Telnet, SNMP, RDP)",
                    "conclusion": "Security risk if externally accessible. Verify authentication is strong and access is restricted by IP.",
                    "confidence": 0.9,
                },
                {
                    "name": "net_default_credentials",
                    "condition": "network device with default credentials",
                    "conclusion": "CRITICAL: Change default credentials immediately. This is a top attack vector.",
                    "confidence": 0.95,
                },
                {
                    "name": "net_unencrypted_traffic",
                    "condition": "unencrypted protocol in use (HTTP, Telnet, FTP, SNMP v1/v2)",
                    "conclusion": "Flag: credentials and data transmitted in cleartext. Upgrade to encrypted alternatives (HTTPS, SSH, SFTP, SNMP v3).",
                    "confidence": 0.9,
                },
                {
                    "name": "net_firewall_misconfig",
                    "condition": "firewall rule allows unexpected traffic",
                    "conclusion": "Document the misconfiguration. Verify rule intent, check for overly broad ALLOW rules, ensure deny-by-default.",
                    "confidence": 0.85,
                },
                {
                    "name": "net_dns_resolution_failure",
                    "condition": "DNS resolution failing",
                    "conclusion": "Check: DNS server reachable? Correct DNS configured? Try alternative DNS (8.8.8.8). Check /etc/resolv.conf or Windows DNS settings.",
                    "confidence": 0.85,
                },
            ],
            knowledge_domains=[
                "networking", "cybersecurity", "wireless", "firewalls",
                "DNS", "routing", "switching", "protocol analysis",
            ],
            confidence_boost=0.15,
        )

    @staticmethod
    def _make_prompt_engineer() -> Specialist:
        return Specialist(
            name="Prompt Engineer",
            role="Expert at crafting effective AI prompts",
            identity_prompt=(
                "You are an expert prompt engineer.\n"
                "Craft precise, effective prompts that get the best results from AI models.\n"
                "Understand: token limits, temperature effects, chain-of-thought reasoning, few-shot learning.\n"
                "Key principles: be specific, provide examples, set constraints, define output format.\n"
                "System messages should establish identity and rules. User messages should be clear tasks.\n"
                "Optimize for: clarity, consistency, desired output format, and avoiding hallucinations.\n"
                "Test prompts iteratively -- small changes can have large effects."
            ),
            trigger_patterns=[
                r"\bprompt\b",
                r"\bimprove\s*prompt\b",
                r"\bsystem\s*(?:prompt|message)\b",
                r"\bbetter\s*instructions?\b",
                r"\boptimize\s*prompt\b",
                r"\bfew.?shot\b",
                r"\bchain.?of.?thought\b",
                r"\btemperature\b.*\b(?:AI|model|GPT|Claude)\b",
                r"\btoken\s*limit\b",
                r"\bsystem\s*role\b",
                r"\bprompt\s*(?:engineer|craft|design|template)\w*\b",
            ],
            preferred_tools=[
                "save_file", "modify_file", "run_python",
            ],
            reasoning_rules=[
                {
                    "name": "pe_vague_prompt",
                    "condition": "prompt lacks specificity or clear constraints",
                    "conclusion": "Add specificity: define the task, expected output format, constraints, and edge cases to handle.",
                    "confidence": 0.85,
                },
                {
                    "name": "pe_too_long",
                    "condition": "prompt is excessively long or repetitive",
                    "conclusion": "Compress: remove redundancy, use concise language, move examples to few-shot format.",
                    "confidence": 0.8,
                },
                {
                    "name": "pe_no_examples",
                    "condition": "prompt provides no examples of desired output",
                    "conclusion": "Add 2-3 few-shot examples showing the exact input-output format expected.",
                    "confidence": 0.85,
                },
                {
                    "name": "pe_no_constraints",
                    "condition": "prompt has no guardrails or constraints",
                    "conclusion": "Add constraints: output length, format, tone, what NOT to do, and how to handle edge cases.",
                    "confidence": 0.8,
                },
            ],
            knowledge_domains=[
                "prompt engineering", "AI models", "NLP", "LLMs",
                "instruction design", "few-shot learning",
            ],
            confidence_boost=0.15,
        )

    @staticmethod
    def _make_task_planner() -> Specialist:
        return Specialist(
            name="Task Planner",
            role="Expert project planner and task decomposer",
            identity_prompt=(
                "You are an expert project planner.\n"
                "Break complex tasks into clear, actionable steps with dependencies.\n"
                "Identify the critical path -- what must happen before what.\n"
                "Estimate complexity: simple (minutes), moderate (hours), complex (days), major (weeks).\n"
                "Find blockers early and address them before dependent tasks.\n"
                "Use a structured format: numbered steps, dependencies noted, estimated time, owner if applicable.\n"
                "Always ask: What could go wrong? What are the unknowns? What should we research first?"
            ),
            trigger_patterns=[
                r"\bplan\b",
                r"\bbreak\s*down\b",
                r"\bsteps?\b.*\b(?:to|for|how)\b",
                r"\bhow\s*(?:to|do\s*I|should)\b",
                r"\bworkflow\b",
                r"\bprocess\b",
                r"\borganiz\w*\b",
                r"\broadmap\b",
                r"\bschedule\b",
                r"\btimeline\b",
                r"\bprioritiz\w*\b",
                r"\bmilestone\b",
                r"\btask\s*(?:list|break|decompos)\w*\b",
                r"\bproject\s*(?:plan|manage)\w*\b",
            ],
            preferred_tools=[
                "set_reminder", "set_timer", "save_file", "web_search",
            ],
            reasoning_rules=[
                {
                    "name": "plan_complex_task",
                    "condition": "task has multiple moving parts or unknowns",
                    "conclusion": "Decompose into subtasks of max 2-hour chunks. Identify dependencies between them.",
                    "confidence": 0.9,
                },
                {
                    "name": "plan_dependencies",
                    "condition": "tasks have dependencies on each other",
                    "conclusion": "Order correctly: blockers first, then dependent tasks. Identify what can be parallelized.",
                    "confidence": 0.9,
                },
                {
                    "name": "plan_unknowns",
                    "condition": "task has significant unknowns or research needed",
                    "conclusion": "Research first before committing to a plan. Time-box the research phase.",
                    "confidence": 0.85,
                },
                {
                    "name": "plan_blockers",
                    "condition": "blocker identified for downstream tasks",
                    "conclusion": "Address blockers immediately. Find workarounds or alternatives. Do not proceed with blocked tasks.",
                    "confidence": 0.9,
                },
            ],
            knowledge_domains=[
                "project management", "task planning", "agile", "productivity",
                "time management", "risk assessment",
            ],
            confidence_boost=0.1,
        )

    @staticmethod
    def _make_generalist() -> Specialist:
        """Fallback specialist for general conversation and tasks."""
        return Specialist(
            name="Generalist",
            role="Well-rounded assistant for general tasks",
            identity_prompt=(
                "You are JARVIS, a versatile and intelligent assistant.\n"
                "Handle this request with your broad general knowledge.\n"
                "Be helpful, accurate, and concise.\n"
                "If the topic becomes specialized, suggest which specialist perspective might help."
            ),
            trigger_patterns=[],  # never triggered by patterns -- only by fallback
            preferred_tools=[
                "web_search", "run_python", "run_command", "save_file",
            ],
            reasoning_rules=[],
            knowledge_domains=["general knowledge"],
            confidence_boost=0.0,
        )


# ═════════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════════

def _flatten_entities(entities: dict) -> list[str]:
    """Flatten an entities dict into a flat list of string values."""
    flat = []
    for key, vals in entities.items():
        flat.append(key)
        if isinstance(vals, list):
            flat.extend(str(v) for v in vals)
        else:
            flat.append(str(vals))
    return flat


# ═════════════════════════════════════════════════════════════════
#  MODULE-LEVEL CONVENIENCE
# ═════════════════════════════════════════════════════════════════

# Singleton instance -- import and use directly
team = SpecialistTeam()


def select_specialist(text: str, entities=None, topic="", intent="") -> Specialist:
    """Module-level convenience for selecting the best specialist."""
    return team.select_specialist(text, entities, topic, intent)


def get_prompt_injection(specialist: Specialist) -> str:
    """Module-level convenience for getting prompt injection."""
    return team.get_prompt_injection(specialist)


def get_reasoning_rules(specialist: Specialist) -> list:
    """Module-level convenience for getting reasoning rules."""
    return team.get_reasoning_rules(specialist)
