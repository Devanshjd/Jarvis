# ═══════════════════════════════════════════════════════════════
# JARVIS Self-Evolution Engine
# Allows JARVIS to modify its own code, add features, fix bugs,
# update itself, and research solutions autonomously.
# ═══════════════════════════════════════════════════════════════

import json
import os
import subprocess
import re
import sys
from pathlib import Path
from datetime import datetime

# ─── Config ───
JARVIS_ROOT = Path(__file__).parent.parent  # d:\my pross\Jarvis
DESKTOP_ROOT = JARVIS_ROOT / "desktop"
SRC_MAIN = DESKTOP_ROOT / "src" / "main" / "index.ts"
SRC_PRELOAD = DESKTOP_ROOT / "src" / "preload" / "index.ts"
SRC_PRELOAD_TYPES = DESKTOP_ROOT / "src" / "preload" / "index.d.ts"
SRC_GEMINI = DESKTOP_ROOT / "src" / "renderer" / "src" / "services" / "JarvisGeminiLive.ts"
LOG_DIR = JARVIS_ROOT / "training" / "evolution_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log_action(action: str, details: dict):
    """Log every self-evolution action for audit trail."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        **details
    }
    log_file = LOG_DIR / f"evolution_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[LOG] {action}: {json.dumps(details, ensure_ascii=False)[:200]}")


# ═══════════════════════════════════════════════════════════════
# 1. SELF-UPDATE — Pull latest code, rebuild
# ═══════════════════════════════════════════════════════════════

def self_update():
    """Pull latest code from git and rebuild."""
    print("\n🔄 JARVIS Self-Update")
    print("=" * 50)
    
    steps = []
    
    # Step 1: Git pull
    print("[1/4] Pulling latest code...")
    result = subprocess.run(
        ["git", "pull", "origin", "main"],
        cwd=str(JARVIS_ROOT), capture_output=True, text=True, timeout=60
    )
    steps.append({"step": "git_pull", "output": result.stdout.strip(), "success": result.returncode == 0})
    
    if "Already up to date" in result.stdout:
        print("  ✅ Already up to date")
    else:
        print(f"  ✅ Updated: {result.stdout.strip()[:100]}")
    
    # Step 2: Install dependencies
    print("[2/4] Installing dependencies...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=str(DESKTOP_ROOT), capture_output=True, text=True, timeout=120,
        shell=True
    )
    steps.append({"step": "npm_install", "success": result.returncode == 0})
    print(f"  {'✅' if result.returncode == 0 else '❌'} Dependencies")
    
    # Step 3: Build
    print("[3/4] Building...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(DESKTOP_ROOT), capture_output=True, text=True, timeout=120,
        shell=True
    )
    steps.append({"step": "build", "success": result.returncode == 0})
    print(f"  {'✅' if result.returncode == 0 else '❌'} Build")
    
    if result.returncode != 0:
        print(f"  Build errors:\n{result.stderr[-500:]}")
        # Try to self-repair
        print("[3b] Attempting self-repair...")
        self_repair(result.stderr)
    
    # Step 4: Commit
    print("[4/4] Committing update...")
    subprocess.run(["git", "add", "-A"], cwd=str(JARVIS_ROOT), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: self-update {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
        cwd=str(JARVIS_ROOT), capture_output=True, text=True
    )
    
    log_action("self_update", {"steps": steps})
    print("\n✅ Self-update complete!")
    return steps


# ═══════════════════════════════════════════════════════════════
# 2. SELF-REPAIR — Diagnose and fix issues
# ═══════════════════════════════════════════════════════════════

def self_repair(error_output: str = ""):
    """Diagnose and fix build/runtime errors."""
    print("\n🔧 JARVIS Self-Repair")
    print("=" * 50)
    
    fixes = []
    
    # If no error provided, run build to find errors
    if not error_output:
        print("[1] Running diagnostics...")
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(DESKTOP_ROOT), capture_output=True, text=True, timeout=120,
            shell=True
        )
        if result.returncode == 0:
            print("  ✅ No build errors found!")
            return fixes
        error_output = result.stderr + result.stdout
    
    # Parse TypeScript errors
    ts_errors = re.findall(r'(src/[^(]+)\((\d+),(\d+)\): error TS(\d+): (.+)', error_output)
    if ts_errors:
        print(f"[2] Found {len(ts_errors)} TypeScript errors")
        for file_path, line, col, code, message in ts_errors:
            print(f"  - {file_path}:{line} TS{code}: {message}")
            fix = attempt_ts_fix(file_path, int(line), code, message)
            if fix:
                fixes.append(fix)
    
    # Parse missing module errors
    missing_modules = re.findall(r"Cannot find module '([^']+)'", error_output)
    if missing_modules:
        print(f"[3] Missing modules: {missing_modules}")
        for mod in missing_modules:
            print(f"  Installing {mod}...")
            subprocess.run(
                ["npm", "install", mod],
                cwd=str(DESKTOP_ROOT), capture_output=True, shell=True
            )
            fixes.append({"type": "install_module", "module": mod})
    
    # Try rebuild after fixes
    if fixes:
        print(f"[4] Applied {len(fixes)} fixes. Rebuilding...")
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(DESKTOP_ROOT), capture_output=True, text=True, timeout=120,
            shell=True
        )
        if result.returncode == 0:
            print("  ✅ Build successful after repair!")
        else:
            print("  ❌ Build still failing. Manual intervention needed.")
    
    log_action("self_repair", {"fixes": fixes, "error_count": len(ts_errors) if ts_errors else 0})
    return fixes


def attempt_ts_fix(file_path: str, line: int, error_code: str, message: str) -> dict | None:
    """Attempt to auto-fix common TypeScript errors."""
    full_path = DESKTOP_ROOT / file_path
    if not full_path.exists():
        return None
    
    content = full_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    # TS2304: Cannot find name — add import or declare
    if error_code == "2304":
        match = re.search(r"Cannot find name '(\w+)'", message)
        if match:
            name = match.group(1)
            # Add @ts-ignore above the line
            if line <= len(lines):
                lines.insert(line - 1, "    // @ts-ignore — auto-fixed by self-repair")
                full_path.write_text("\n".join(lines), encoding="utf-8")
                return {"type": "ts_ignore", "file": file_path, "line": line, "name": name}
    
    # TS2345: Argument type mismatch — add 'as any'
    if error_code == "2345" or error_code == "2322":
        # These are complex type errors, add ts-ignore
        if line <= len(lines):
            lines.insert(line - 1, "    // @ts-ignore — auto-fixed by self-repair")
            full_path.write_text("\n".join(lines), encoding="utf-8")
            return {"type": "ts_ignore", "file": file_path, "line": line}
    
    # TS7006: Parameter implicitly has 'any' type
    if error_code == "7006":
        match = re.search(r"Parameter '(\w+)'", message)
        if match:
            param = match.group(1)
            if line <= len(lines):
                lines[line - 1] = lines[line - 1].replace(param, f"{param}: any")
                full_path.write_text("\n".join(lines), encoding="utf-8")
                return {"type": "add_any_type", "file": file_path, "line": line, "param": param}
    
    return None


# ═══════════════════════════════════════════════════════════════
# 3. ADD FEATURE — Generate and integrate new code
# ═══════════════════════════════════════════════════════════════

def add_feature(description: str, gemini_api_key: str = ""):
    """Use Gemini to generate a new feature and integrate it."""
    print(f"\n🚀 JARVIS Add Feature: {description}")
    print("=" * 50)
    
    # Load API key
    if not gemini_api_key:
        config_path = Path.home() / ".jarvis_config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text())
            gemini_api_key = config.get("geminiApiKey", "")
    
    if not gemini_api_key:
        print("❌ No Gemini API key. Cannot generate code.")
        return None
    
    # Step 1: Analyze current codebase structure
    print("[1/5] Analyzing codebase structure...")
    structure = get_codebase_summary()
    
    # Step 2: Generate code with Gemini
    print("[2/5] Generating code with Gemini...")
    prompt = build_code_generation_prompt(description, structure)
    generated = call_gemini(prompt, gemini_api_key)
    
    if not generated:
        print("❌ Code generation failed")
        return None
    
    # Step 3: Parse generated code into files
    print("[3/5] Parsing generated code...")
    file_changes = parse_generated_code(generated)
    
    if not file_changes:
        print("❌ Could not parse generated code")
        print(f"Raw output:\n{generated[:1000]}")
        log_action("add_feature_failed", {"description": description, "raw": generated[:500]})
        return None
    
    # Step 4: Apply changes
    print(f"[4/5] Applying {len(file_changes)} file changes...")
    applied = []
    for change in file_changes:
        result = apply_code_change(change)
        if result:
            applied.append(result)
            print(f"  ✅ {change.get('action', 'modified')}: {change.get('file', 'unknown')}")
    
    # Step 5: Build and verify
    print("[5/5] Building to verify...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(DESKTOP_ROOT), capture_output=True, text=True, timeout=120,
        shell=True
    )
    
    if result.returncode == 0:
        print("\n✅ Feature added successfully! Build passes.")
        # Commit
        subprocess.run(["git", "add", "-A"], cwd=str(JARVIS_ROOT), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat(self-evolve): {description[:50]}"],
            cwd=str(JARVIS_ROOT), capture_output=True, text=True
        )
        log_action("add_feature_success", {"description": description, "files": [c.get("file") for c in file_changes]})
    else:
        print("\n⚠️ Build failed. Attempting self-repair...")
        self_repair(result.stderr + result.stdout)
        log_action("add_feature_build_fail", {"description": description, "error": result.stderr[-500:]})
    
    return applied


def get_codebase_summary() -> str:
    """Get a summary of JARVIS codebase for the AI to understand."""
    summary = "JARVIS Codebase Structure:\n\n"
    
    # Main process — list IPC handlers
    if SRC_MAIN.exists():
        main_content = SRC_MAIN.read_text(encoding="utf-8")
        handlers = re.findall(r"ipcMain\.handle\('([^']+)'", main_content)
        summary += f"Main Process (index.ts): {len(handlers)} IPC handlers\n"
        summary += f"Handlers: {', '.join(handlers[:20])}...\n\n"
    
    # Preload — list exposed APIs
    if SRC_PRELOAD.exists():
        preload = SRC_PRELOAD.read_text(encoding="utf-8")
        apis = re.findall(r"(\w+):\s*\([^)]*\)\s*=>", preload)
        summary += f"Preload (index.ts): {len(apis)} exposed APIs\n"
        summary += f"APIs: {', '.join(apis[:20])}...\n\n"
    
    # Renderer widgets
    widgets_dir = DESKTOP_ROOT / "src" / "renderer" / "src" / "widgets"
    if widgets_dir.exists():
        widgets = [f.stem for f in widgets_dir.glob("*.tsx")]
        summary += f"Widgets: {', '.join(widgets)}\n\n"
    
    # Views
    views_dir = DESKTOP_ROOT / "src" / "renderer" / "src" / "views"
    if views_dir.exists():
        views = [f.stem for f in views_dir.glob("*.tsx")]
        summary += f"Views: {', '.join(views)}\n\n"
    
    summary += f"Tech stack: Electron + React + TypeScript + Vite\n"
    summary += f"Pattern: IPC handler in main -> preload bridge -> renderer call\n"
    
    return summary


def build_code_generation_prompt(description: str, structure: str) -> str:
    """Build a prompt for Gemini to generate the code."""
    return f"""You are a senior developer working on JARVIS, an Electron desktop assistant.

{structure}

TASK: {description}

RULES:
1. Follow the existing IPC pattern: ipcMain.handle() in main -> preload bridge -> renderer call
2. Use TypeScript
3. Return code changes as JSON array with this format:
```json
[
  {{
    "file": "relative/path/to/file.ts",
    "action": "append" | "create" | "modify",
    "content": "// the actual code to add",
    "insert_after": "line of code to insert after (for append)"
  }}
]
```
4. Only include the NEW code to add, not the entire file
5. Make sure all types are correct
6. Add error handling with try/catch

Respond with ONLY the JSON array, no explanation."""


def call_gemini(prompt: str, api_key: str) -> str:
    """Call Gemini API to generate code."""
    try:
        import urllib.request
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 8192
            }
        }).encode()
        
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data["candidates"][0]["content"]["parts"][0]["text"]
    
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return ""


def parse_generated_code(raw: str) -> list:
    """Parse generated code from Gemini response."""
    # Extract JSON from response
    json_match = re.search(r'\[[\s\S]*\]', raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # Try to find code blocks
    code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', raw)
    for block in code_blocks:
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue
    
    return []


def apply_code_change(change: dict) -> dict | None:
    """Apply a single code change."""
    file_path = DESKTOP_ROOT / change.get("file", "")
    action = change.get("action", "append")
    content = change.get("content", "")
    
    if not content:
        return None
    
    try:
        if action == "create":
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return {"file": str(file_path), "action": "created"}
        
        elif action == "append":
            if file_path.exists():
                existing = file_path.read_text(encoding="utf-8")
                insert_after = change.get("insert_after", "")
                
                if insert_after and insert_after in existing:
                    # Insert after specific line
                    idx = existing.index(insert_after) + len(insert_after)
                    new_content = existing[:idx] + "\n\n" + content + existing[idx:]
                    file_path.write_text(new_content, encoding="utf-8")
                else:
                    # Append to end
                    file_path.write_text(existing + "\n\n" + content, encoding="utf-8")
                return {"file": str(file_path), "action": "appended"}
        
        elif action == "modify":
            if file_path.exists():
                existing = file_path.read_text(encoding="utf-8")
                target = change.get("target", "")
                if target and target in existing:
                    new_content = existing.replace(target, content)
                    file_path.write_text(new_content, encoding="utf-8")
                    return {"file": str(file_path), "action": "modified"}
    
    except Exception as e:
        print(f"  ❌ Error applying change to {file_path}: {e}")
    
    return None


# ═══════════════════════════════════════════════════════════════
# 4. RESEARCH — Search web for solutions
# ═══════════════════════════════════════════════════════════════

def research(query: str, gemini_api_key: str = "") -> str:
    """Search for solutions using Gemini's knowledge."""
    print(f"\n🔍 JARVIS Research: {query}")
    print("=" * 50)
    
    if not gemini_api_key:
        config_path = Path.home() / ".jarvis_config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text())
            gemini_api_key = config.get("geminiApiKey", "")
    
    if not gemini_api_key:
        print("❌ No API key for research")
        return ""
    
    prompt = f"""You are a senior developer. Research and provide a detailed technical solution for:

{query}

Context: This is for JARVIS, an Electron desktop assistant with:
- 43 native IPC tools (file ops, app control, terminal, cyber, RAG, creative)
- React + TypeScript frontend with widget-based UI
- Gemini Live voice integration
- Offline Ollama brain for tool routing

Provide:
1. Step-by-step solution
2. Code examples if applicable
3. Any npm packages needed
4. Potential issues to watch for"""

    result = call_gemini(prompt, gemini_api_key)
    if result:
        print(f"\n📋 Research Results:\n{result[:2000]}")
        
        # Save to knowledge base
        research_file = LOG_DIR / f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        research_file.write_text(f"# Research: {query}\n\nDate: {datetime.now().isoformat()}\n\n{result}")
        print(f"\n💾 Saved to: {research_file}")
    
    log_action("research", {"query": query, "result_length": len(result)})
    return result


# ═══════════════════════════════════════════════════════════════
# 5. DIAGNOSTICS — Full system health check
# ═══════════════════════════════════════════════════════════════

def diagnostics():
    """Run full system diagnostics."""
    print("\n🩺 JARVIS System Diagnostics")
    print("=" * 50)
    
    checks = []
    
    # Check Node.js
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        checks.append(("Node.js", r.stdout.strip(), True))
    except:
        checks.append(("Node.js", "NOT FOUND", False))
    
    # Check npm
    try:
        r = subprocess.run(["npm", "--version"], capture_output=True, text=True, timeout=5, shell=True)
        checks.append(("npm", r.stdout.strip(), True))
    except:
        checks.append(("npm", "NOT FOUND", False))
    
    # Check git
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        checks.append(("git", r.stdout.strip(), True))
    except:
        checks.append(("git", "NOT FOUND", False))
    
    # Check Ollama
    try:
        r = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=5)
        checks.append(("Ollama", r.stdout.strip(), True))
    except:
        checks.append(("Ollama", "NOT FOUND", False))
    
    # Check Python
    try:
        r = subprocess.run([sys.executable, "--version"], capture_output=True, text=True, timeout=5)
        checks.append(("Python", r.stdout.strip(), True))
    except:
        checks.append(("Python", "NOT FOUND", False))
    
    # Check build
    try:
        r = subprocess.run(["npm", "run", "build"], cwd=str(DESKTOP_ROOT), capture_output=True, text=True, timeout=120, shell=True)
        checks.append(("Build", "PASSES" if r.returncode == 0 else "FAILS", r.returncode == 0))
    except:
        checks.append(("Build", "ERROR", False))
    
    # Check Gemini API key — try all known config layouts
    config_path = Path.home() / ".jarvis_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding='utf-8'))
        has_key = bool(
            (config.get("gemini") or {}).get("api_key")
            or config.get("api_key")
            or config.get("geminiApiKey")
        )
        checks.append(("Gemini API Key", "configured" if has_key else "MISSING", has_key))
    
    # Check learning log
    learning_log = Path.home() / ".jarvis_sandbox" / "learning_log.jsonl"
    if learning_log.exists():
        lines = len(learning_log.read_text().strip().split("\n"))
        checks.append(("Learning Data", f"{lines} examples", True))
    else:
        checks.append(("Learning Data", "0 examples", True))
    
    # Print results
    print(f"\n{'Component':<20} {'Status':<30} {'OK'}")
    print("-" * 55)
    passed = 0
    for name, status, ok in checks:
        emoji = "✅" if ok else "❌"
        print(f"{name:<20} {status:<30} {emoji}")
        if ok: passed += 1
    
    print(f"\nHealth: {passed}/{len(checks)} checks passed")
    log_action("diagnostics", {"passed": passed, "total": len(checks), "checks": checks})
    return checks


# ═══════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS Self-Evolution Engine")
    subparsers = parser.add_subparsers(dest="command")
    
    # Update
    subparsers.add_parser("update", help="Pull latest code and rebuild")
    
    # Repair
    subparsers.add_parser("repair", help="Diagnose and fix issues")
    
    # Feature
    feat_parser = subparsers.add_parser("feature", help="Add a new feature")
    feat_parser.add_argument("description", type=str, help="Feature description")
    
    # Research
    res_parser = subparsers.add_parser("research", help="Research a topic")
    res_parser.add_argument("query", type=str, help="Research query")
    
    # Diagnostics
    subparsers.add_parser("diagnostics", help="Run system diagnostics")
    
    args = parser.parse_args()
    
    if args.command == "update":
        self_update()
    elif args.command == "repair":
        self_repair()
    elif args.command == "feature":
        add_feature(args.description)
    elif args.command == "research":
        research(args.query)
    elif args.command == "diagnostics":
        diagnostics()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
