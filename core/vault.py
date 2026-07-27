"""
J.A.R.V.I.S — Knowledge Vault  (Obsidian-native memory)

JARVIS's durable, human-browsable brain: a folder of Markdown notes with YAML
frontmatter and [[wikilinks]] — openable in Obsidian, editable by hand, and
recallable by JARVIS. This is the persistent form of the multi-agent blackboard.

The loop it enables:
  · capture  — write a decision / fact / finding as a note (carefully — durable
               things, not chatter).
  · recall   — pull the right note back later by meaning/keywords.
  · correct  — you open Obsidian, fix a wrong note, and JARVIS now knows better.

Honest scope: this makes JARVIS better-INFORMED (retrieval-augmented), not
retrained. Recall feeds facts into its reasoning; the reasoning is still the
model. Search here is keyword-relevance and fully offline; sqlite-vec / the
existing vector_memory can layer semantic recall on top later.

Vault location: $JARVIS_VAULT, else ~/JarvisVault.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional


def vault_root() -> Path:
    env = os.environ.get("JARVIS_VAULT", "").strip()
    return Path(env) if env else (Path.home() / "JarvisVault")


_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class Note:
    title: str
    folder: str
    body: str
    tags: list[str] = field(default_factory=list)
    type: str = "note"
    path: Optional[Path] = None

    @property
    def links(self) -> list[str]:
        return _WIKILINK.findall(self.body)


class Vault:
    FOLDERS = ("Architecture", "Decisions", "Security", "Projects",
               "Research", "Lessons", "Datasets")

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else vault_root()

    # ── setup ────────────────────────────────────────────────────────────
    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for f in self.FOLDERS:
            (self.root / f).mkdir(exist_ok=True)
        home = self.root / "Home.md"
        if not home.exists():
            links = "\n".join(f"- [[{f}]]" for f in self.FOLDERS)
            home.write_text(
                "---\ntitle: Home\ntype: index\n---\n\n"
                "# JARVIS Knowledge Vault\n\n"
                "The durable, correctable brain. Open the graph view to see how "
                "it connects.\n\n## Sections\n" + links + "\n",
                encoding="utf-8")

    # ── capture ──────────────────────────────────────────────────────────
    @staticmethod
    def _slug(title: str) -> str:
        return re.sub(r"[^\w\- ]", "", title).strip()[:80] or "note"

    def write(self, folder: str, title: str, body: str, *,
              tags: Optional[list[str]] = None, type: str = "note",
              mode: str = "create") -> Path:
        """Create (or append to) a note. Returns its path."""
        self.ensure()
        fdir = self.root / folder
        fdir.mkdir(parents=True, exist_ok=True)
        path = fdir / f"{self._slug(title)}.md"

        if mode == "append" and path.exists():
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n" + body.strip() + "\n")
            return path

        fm = ("---\n"
              f"title: {title}\n"
              f"type: {type}\n"
              f"tags: [{', '.join(tags or [])}]\n"
              f"updated: {date.today().isoformat()}\n"
              "---\n\n")
        path.write_text(fm + body.strip() + "\n", encoding="utf-8")
        return path

    # ── read ─────────────────────────────────────────────────────────────
    def _parse(self, path: Path) -> Note:
        raw = path.read_text(encoding="utf-8", errors="replace")
        title, ttype, tags, body = path.stem, "note", [], raw
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
        if m:
            head, body = m.group(1), m.group(2).strip()
            for line in head.splitlines():
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip() or title
                elif line.startswith("type:"):
                    ttype = line.split(":", 1)[1].strip() or ttype
                elif line.startswith("tags:"):
                    tags = [t.strip() for t in
                            line.split(":", 1)[1].strip().strip("[]").split(",") if t.strip()]
        return Note(title=title, folder=path.parent.name, body=body,
                    tags=tags, type=ttype, path=path)

    def list(self, folder: Optional[str] = None) -> list[Note]:
        base = (self.root / folder) if folder else self.root
        if not base.exists():
            return []
        return [self._parse(p) for p in sorted(base.rglob("*.md"))
                if p.name != "Home.md"]

    # ── recall ───────────────────────────────────────────────────────────
    def search(self, query: str, k: int = 5) -> list[tuple[int, Note]]:
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
        if not terms:
            return []
        scored: list[tuple[int, Note]] = []
        for note in self.list():
            body_l, title_l, tags_l = note.body.lower(), note.title.lower(), " ".join(note.tags).lower()
            score = sum(body_l.count(t) for t in terms)
            score += 4 * sum(t in title_l for t in terms)   # title weight
            score += 2 * sum(t in tags_l for t in terms)    # tag weight
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]

    def recall(self, query: str, k: int = 3) -> str:
        """A context block JARVIS can prepend to its reasoning."""
        hits = self.search(query, k)
        if not hits:
            return ""
        out = ["[From JARVIS's knowledge vault]"]
        for _score, note in hits:
            snippet = note.body.strip().split("\n\n")[0]
            snippet = re.sub(r"\s+", " ", snippet)[:320]
            out.append(f"## {note.title}  ({note.folder})\n{snippet}")
        return "\n\n".join(out)

    def stats(self) -> dict:
        notes = self.list()
        return {
            "notes": len(notes),
            "links": sum(len(n.links) for n in notes),
            "folders": {f: len(self.list(f)) for f in self.FOLDERS},
            "root": str(self.root),
        }
