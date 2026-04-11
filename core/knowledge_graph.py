"""
J.A.R.V.I.S — Knowledge Graph (SQLite)
Replaces flat JSON memory with a proper graph database.

Stores:
    - Entities: people, tools, targets, vulnerabilities, projects
    - Facts: key-value properties on entities
    - Relationships: typed connections between entities
    - Timeline: when things were learned, for decay/relevance

Why SQLite:
    - Zero setup, single file, fast, concurrent-safe
    - Full-text search built in
    - Survives crashes (WAL mode)
    - Queries are instant even with 100K+ entries
"""

import os
import re
import sqlite3
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger("jarvis.knowledge_graph")

DB_PATH = Path.home() / ".jarvis_knowledge.db"


class KnowledgeGraph:
    """
    SQLite-backed knowledge graph with entities, facts, and relationships.

    Usage:
        kg = KnowledgeGraph()
        kg.add_entity("example.com", "target", {"ip": "93.184.216.34"})
        kg.add_fact("example.com", "runs", "Apache 2.4")
        kg.add_relationship("example.com", "has_subdomain", "api.example.com")
        results = kg.query("what do I know about example.com")
    """

    def __init__(self, db_path: str = None):
        self._db_path = str(db_path or DB_PATH)
        self._local = threading.local()
        self._init_db()
        logger.info("Knowledge graph online — %s", self._db_path)

    @contextmanager
    def _conn(self):
        """Thread-safe connection — each thread gets its own."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        yield self._local.conn

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'unknown',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    access_count INTEGER DEFAULT 0,
                    UNIQUE(name, type)
                );

                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    predicate TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 0.8,
                    source TEXT DEFAULT 'conversation',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id INTEGER NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id INTEGER NOT NULL,
                    confidence REAL DEFAULT 0.8,
                    source TEXT DEFAULT 'conversation',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (subject_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (object_id) REFERENCES entities(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS timeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    entity_name TEXT,
                    data TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
                CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
                CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(entity_id);
                CREATE INDEX IF NOT EXISTS idx_facts_predicate ON facts(predicate);
                CREATE INDEX IF NOT EXISTS idx_rels_subject ON relationships(subject_id);
                CREATE INDEX IF NOT EXISTS idx_rels_object ON relationships(object_id);
                CREATE INDEX IF NOT EXISTS idx_timeline_entity ON timeline(entity_name);
            """)
            conn.commit()

    # ══════════════════════════════════════════════════════════════
    #  ENTITIES
    # ══════════════════════════════════════════════════════════════

    def add_entity(self, name: str, entity_type: str, facts: dict = None) -> int:
        """Add or update an entity. Returns entity ID."""
        name = name.strip().lower()
        entity_type = entity_type.strip().lower()

        with self._conn() as conn:
            # Upsert
            conn.execute("""
                INSERT INTO entities (name, type)
                VALUES (?, ?)
                ON CONFLICT(name, type)
                DO UPDATE SET updated_at = datetime('now'),
                             access_count = access_count + 1
            """, (name, entity_type))

            entity_id = conn.execute(
                "SELECT id FROM entities WHERE name=? AND type=?",
                (name, entity_type)
            ).fetchone()["id"]

            # Add facts if provided
            if facts:
                for predicate, value in facts.items():
                    self._add_fact_internal(conn, entity_id, predicate, str(value))

            conn.commit()
            return entity_id

    def get_entity(self, name: str) -> dict | None:
        """Get an entity with all its facts."""
        name = name.strip().lower()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM entities WHERE name=?", (name,)
            ).fetchone()
            if not row:
                return None

            # Update access count
            conn.execute(
                "UPDATE entities SET access_count = access_count + 1 WHERE id=?",
                (row["id"],)
            )

            facts = conn.execute(
                "SELECT predicate, value, confidence FROM facts WHERE entity_id=?",
                (row["id"],)
            ).fetchall()

            conn.commit()
            return {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "created": row["created_at"],
                "facts": {f["predicate"]: f["value"] for f in facts},
            }

    def search_entities(self, query: str, entity_type: str = None,
                        limit: int = 20) -> list[dict]:
        """Search entities by name substring."""
        query = query.strip().lower()
        with self._conn() as conn:
            if entity_type:
                rows = conn.execute(
                    "SELECT * FROM entities WHERE name LIKE ? AND type=? "
                    "ORDER BY access_count DESC LIMIT ?",
                    (f"%{query}%", entity_type, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM entities WHERE name LIKE ? "
                    "ORDER BY access_count DESC LIMIT ?",
                    (f"%{query}%", limit)
                ).fetchall()

            return [{"name": r["name"], "type": r["type"],
                     "accessed": r["access_count"]} for r in rows]

    # ══════════════════════════════════════════════════════════════
    #  FACTS
    # ══════════════════════════════════════════════════════════════

    def add_fact(self, entity_name: str, predicate: str, value: str,
                 entity_type: str = "unknown", confidence: float = 0.8,
                 source: str = "conversation"):
        """Add a fact about an entity. Creates entity if needed."""
        entity_id = self.add_entity(entity_name, entity_type)
        with self._conn() as conn:
            self._add_fact_internal(conn, entity_id, predicate, value,
                                   confidence, source)
            conn.commit()

    def _add_fact_internal(self, conn, entity_id: int, predicate: str,
                          value: str, confidence: float = 0.8,
                          source: str = "conversation"):
        """Internal: add fact within existing connection."""
        # Check for existing fact with same predicate
        existing = conn.execute(
            "SELECT id FROM facts WHERE entity_id=? AND predicate=? AND value=?",
            (entity_id, predicate, value)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE facts SET confidence=MAX(confidence, ?), source=? WHERE id=?",
                (confidence, source, existing["id"])
            )
        else:
            conn.execute(
                "INSERT INTO facts (entity_id, predicate, value, confidence, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (entity_id, predicate, value, confidence, source)
            )

    def get_facts(self, entity_name: str) -> list[dict]:
        """Get all facts about an entity."""
        entity_name = entity_name.strip().lower()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT f.predicate, f.value, f.confidence, f.source, f.created_at
                FROM facts f
                JOIN entities e ON f.entity_id = e.id
                WHERE e.name = ?
                ORDER BY f.confidence DESC
            """, (entity_name,)).fetchall()

            return [dict(r) for r in rows]

    # ══════════════════════════════════════════════════════════════
    #  RELATIONSHIPS
    # ══════════════════════════════════════════════════════════════

    def add_relationship(self, subject: str, predicate: str, obj: str,
                         subject_type: str = "unknown",
                         obj_type: str = "unknown",
                         confidence: float = 0.8):
        """Add a relationship between two entities."""
        subj_id = self.add_entity(subject, subject_type)
        obj_id = self.add_entity(obj, obj_type)

        with self._conn() as conn:
            # Avoid duplicates
            existing = conn.execute(
                "SELECT id FROM relationships "
                "WHERE subject_id=? AND predicate=? AND object_id=?",
                (subj_id, predicate, obj_id)
            ).fetchone()

            if not existing:
                conn.execute(
                    "INSERT INTO relationships "
                    "(subject_id, predicate, object_id, confidence) "
                    "VALUES (?, ?, ?, ?)",
                    (subj_id, predicate, obj_id, confidence)
                )
            conn.commit()

    def get_relationships(self, entity_name: str,
                         direction: str = "both") -> list[dict]:
        """Get relationships for an entity (outgoing, incoming, or both)."""
        entity_name = entity_name.strip().lower()
        results = []
        with self._conn() as conn:
            eid = conn.execute(
                "SELECT id FROM entities WHERE name=?", (entity_name,)
            ).fetchone()
            if not eid:
                return []
            eid = eid["id"]

            if direction in ("out", "both"):
                rows = conn.execute("""
                    SELECT e.name as object, r.predicate, r.confidence
                    FROM relationships r
                    JOIN entities e ON r.object_id = e.id
                    WHERE r.subject_id = ?
                """, (eid,)).fetchall()
                for r in rows:
                    results.append({
                        "direction": "out",
                        "predicate": r["predicate"],
                        "target": r["object"],
                        "confidence": r["confidence"],
                    })

            if direction in ("in", "both"):
                rows = conn.execute("""
                    SELECT e.name as subject, r.predicate, r.confidence
                    FROM relationships r
                    JOIN entities e ON r.subject_id = e.id
                    WHERE r.object_id = ?
                """, (eid,)).fetchall()
                for r in rows:
                    results.append({
                        "direction": "in",
                        "predicate": r["predicate"],
                        "source": r["subject"],
                        "confidence": r["confidence"],
                    })

        return results

    # ══════════════════════════════════════════════════════════════
    #  TIMELINE
    # ══════════════════════════════════════════════════════════════

    def log_event(self, event_type: str, description: str,
                  entity_name: str = None, data: str = None):
        """Log a timestamped event."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO timeline (event_type, description, entity_name, data) "
                "VALUES (?, ?, ?, ?)",
                (event_type, description, entity_name, data)
            )
            conn.commit()

    def get_timeline(self, entity_name: str = None, days: int = 7,
                     limit: int = 50) -> list[dict]:
        """Get recent timeline events."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            if entity_name:
                rows = conn.execute(
                    "SELECT * FROM timeline WHERE entity_name=? "
                    "AND created_at > ? ORDER BY created_at DESC LIMIT ?",
                    (entity_name.lower(), cutoff, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM timeline WHERE created_at > ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (cutoff, limit)
                ).fetchall()
            return [dict(r) for r in rows]

    # ══════════════════════════════════════════════════════════════
    #  SMART QUERIES — The real intelligence
    # ══════════════════════════════════════════════════════════════

    def query_everything(self, topic: str) -> dict:
        """Get everything JARVIS knows about a topic — entity + facts + relationships + timeline."""
        topic = topic.strip().lower()
        entity = self.get_entity(topic)
        facts = self.get_facts(topic)
        rels = self.get_relationships(topic)
        timeline = self.get_timeline(topic, days=30)

        return {
            "entity": entity,
            "facts": facts,
            "relationships": rels,
            "timeline": timeline,
        }

    def find_connections(self, entity_a: str, entity_b: str) -> list[dict]:
        """Find how two entities are connected (up to 2 hops)."""
        a = entity_a.strip().lower()
        b = entity_b.strip().lower()
        connections = []

        with self._conn() as conn:
            # Direct connection
            rows = conn.execute("""
                SELECT r.predicate, 'direct' as path
                FROM relationships r
                JOIN entities ea ON r.subject_id = ea.id
                JOIN entities eb ON r.object_id = eb.id
                WHERE ea.name = ? AND eb.name = ?
                UNION
                SELECT r.predicate, 'reverse' as path
                FROM relationships r
                JOIN entities ea ON r.object_id = ea.id
                JOIN entities eb ON r.subject_id = eb.id
                WHERE ea.name = ? AND eb.name = ?
            """, (a, b, a, b)).fetchall()

            for r in rows:
                connections.append({
                    "type": "direct",
                    "predicate": r["predicate"],
                    "path": r["path"],
                })

            # 2-hop connection (A → X → B)
            if not connections:
                rows = conn.execute("""
                    SELECT em.name as middle, r1.predicate as p1, r2.predicate as p2
                    FROM relationships r1
                    JOIN relationships r2 ON r1.object_id = r2.subject_id
                    JOIN entities ea ON r1.subject_id = ea.id
                    JOIN entities em ON r1.object_id = em.id
                    JOIN entities eb ON r2.object_id = eb.id
                    WHERE ea.name = ? AND eb.name = ?
                    LIMIT 10
                """, (a, b)).fetchall()

                for r in rows:
                    connections.append({
                        "type": "2-hop",
                        "path": f"{a} --{r['p1']}--> {r['middle']} --{r['p2']}--> {b}",
                    })

        return connections

    def get_context_for_llm(self, topic: str = None, max_facts: int = 30) -> str:
        """Generate knowledge context for LLM injection."""
        parts = []

        if topic:
            data = self.query_everything(topic)
            if data["entity"]:
                parts.append(f"[KNOWLEDGE about '{topic}']")
                parts.append(f"  Type: {data['entity']['type']}")
                for pred, val in list(data["entity"].get("facts", {}).items())[:15]:
                    parts.append(f"  {pred}: {val}")
                for rel in data["relationships"][:10]:
                    if rel["direction"] == "out":
                        parts.append(f"  {rel['predicate']} → {rel['target']}")
                    else:
                        parts.append(f"  {rel['source']} → {rel['predicate']}")

        # Also inject recent important entities
        with self._conn() as conn:
            recent = conn.execute(
                "SELECT name, type FROM entities "
                "ORDER BY updated_at DESC LIMIT 10"
            ).fetchall()
            if recent:
                parts.append("\n[RECENT KNOWLEDGE]")
                for r in recent:
                    facts = conn.execute(
                        "SELECT predicate, value FROM facts "
                        "WHERE entity_id = (SELECT id FROM entities WHERE name=? LIMIT 1) "
                        "ORDER BY confidence DESC LIMIT 3",
                        (r["name"],)
                    ).fetchall()
                    if facts:
                        fact_str = ", ".join(f"{f['predicate']}={f['value']}" for f in facts)
                        parts.append(f"  {r['name']} ({r['type']}): {fact_str}")

        return "\n".join(parts) if parts else ""

    # ══════════════════════════════════════════════════════════════
    #  AUTO-EXTRACTION — Extract from conversations
    # ══════════════════════════════════════════════════════════════

    # Patterns for extracting structured knowledge from text
    _EXTRACT_PATTERNS = [
        # Domains and IPs
        (r"(?:target|domain|site|website)\s+(?:is\s+)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,})",
         "target", "identified_as"),
        (r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", "ip_address", "detected"),
        # Technologies
        (r"(?:running|uses?|powered by|built with)\s+([A-Za-z][\w.-]+(?:\s+[\d.]+)?)",
         "technology", "runs"),
        # Vulnerabilities
        (r"(CVE-\d{4}-\d+)", "vulnerability", "found"),
        (r"(?:found|detected|discovered)\s+(?:an?\s+)?(\w+\s+(?:vulnerability|injection|xss|sqli|rce))",
         "vulnerability", "found"),
        # Ports
        (r"port\s+(\d+)\s+(?:is\s+)?open", "port", "open_on"),
        # Subdomains
        (r"subdomain[s]?\s*:?\s*([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,})",
         "subdomain", "subdomain_of"),
        # User facts
        (r"(?:my name is|I'm|call me)\s+([A-Z][a-z]+)", "person", "name_is"),
        (r"I\s+(?:work|study)\s+(?:at|in)\s+(.+?)(?:\.|,|$)", "person", "works_at"),
        (r"I\s+(?:like|prefer|love)\s+(.+?)(?:\.|,|$)", "person", "likes"),
    ]

    def extract_from_text(self, text: str, source: str = "conversation"):
        """Auto-extract entities, facts, and relationships from text."""
        extracted = 0
        for pattern, entity_type, predicate in self._EXTRACT_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1).strip()
                if len(value) < 2 or len(value) > 200:
                    continue

                self.add_entity(value, entity_type)
                self.add_fact(value, predicate, "true",
                            entity_type=entity_type, source=source)
                extracted += 1

        return extracted

    def extract_scan_results(self, tool_name: str, target: str,
                            results: str):
        """Extract structured knowledge from security scan output."""
        target = target.strip().lower()
        self.add_entity(target, "target")

        if tool_name in ("recon", "full_recon"):
            # Extract subdomains
            for match in re.finditer(
                r"([a-zA-Z0-9][-a-zA-Z0-9]*\." + re.escape(target) + r")",
                results
            ):
                sub = match.group(1).lower()
                self.add_entity(sub, "subdomain")
                self.add_relationship(target, "has_subdomain", sub,
                                     "target", "subdomain")

            # Extract technologies
            for match in re.finditer(
                r"(?:Server|X-Powered-By|Detected):\s*(.+?)(?:\n|$)", results
            ):
                tech = match.group(1).strip()
                if tech:
                    self.add_fact(target, "technology", tech, source="scan")

            # Extract open paths
            for match in re.finditer(r"\[FOUND\]\s+(/\S+)", results):
                path = match.group(1)
                self.add_fact(target, "exposed_path", path, source="scan")

        elif tool_name in ("port_scan",):
            for match in re.finditer(r"(\d+)/tcp\s+OPEN\s+(\w+)", results):
                port, service = match.groups()
                self.add_fact(target, f"port_{port}", service, source="scan")

        elif tool_name in ("xss_test", "sqli_test"):
            if "REFLECTED" in results or "SQL ERROR" in results:
                vuln_type = "xss" if "xss" in tool_name else "sqli"
                self.add_fact(target, f"vulnerable_to", vuln_type, source="scan")
                self.log_event("vulnerability_found", f"{vuln_type} on {target}",
                              target)

        elif tool_name in ("ssl_check",):
            if "EXPIRED" in results:
                self.add_fact(target, "ssl_expired", "true", source="scan")
            if "HSTS" in results and "No HSTS" in results:
                self.add_fact(target, "missing_hsts", "true", source="scan")

        # Always log the scan
        self.log_event("scan", f"{tool_name} on {target}", target)

    # ══════════════════════════════════════════════════════════════
    #  STATS
    # ══════════════════════════════════════════════════════════════

    def get_stats(self) -> dict:
        with self._conn() as conn:
            entities = conn.execute("SELECT COUNT(*) as c FROM entities").fetchone()["c"]
            facts = conn.execute("SELECT COUNT(*) as c FROM facts").fetchone()["c"]
            rels = conn.execute("SELECT COUNT(*) as c FROM relationships").fetchone()["c"]
            events = conn.execute("SELECT COUNT(*) as c FROM timeline").fetchone()["c"]
            types = conn.execute(
                "SELECT type, COUNT(*) as c FROM entities GROUP BY type"
            ).fetchall()

            return {
                "entities": entities,
                "facts": facts,
                "relationships": rels,
                "timeline_events": events,
                "entity_types": {r["type"]: r["c"] for r in types},
            }
