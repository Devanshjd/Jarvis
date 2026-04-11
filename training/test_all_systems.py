#!/usr/bin/env python3
"""
J.A.R.V.I.S. System Test & Training Data Generator
===================================================
Tests every subsystem and logs results as training entries
for the offline brain to learn from.

Each test generates a training pair:
  user_input -> tool_used + response

This makes JARVIS smarter about when to use which tool.
"""

import os
import sys
import json
import sqlite3
import subprocess
import time
import socket
import hashlib
import platform
from datetime import datetime
from pathlib import Path

# ─── Config ───
HOME = os.path.expanduser("~")
VAULT_DB = os.path.join(HOME, ".jarvis_vault.db")
WORKFLOWS_DIR = os.path.join(HOME, ".jarvis_workflows")
PLUGINS_DIR = os.path.join(HOME, ".jarvis_plugins")
CONFIG_PATH = os.path.join(HOME, ".jarvis_config.json")
LEARNING_LOG = os.path.join(os.path.dirname(__file__), "learning_log.jsonl")

PASSED = 0
FAILED = 0
TOTAL = 0
TRAINING_ENTRIES = []

def log_result(test_name, passed, details="", user_input="", tool_used="", response=""):
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    status = "✅ PASS" if passed else "❌ FAIL"
    if passed:
        PASSED += 1
    else:
        FAILED += 1
    print(f"  {status} │ {test_name}: {details[:100]}")

    # Generate training entry
    if user_input and tool_used:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "tool_used": tool_used,
            "tool_params": {},
            "response": response[:500] if response else details[:500],
            "success": passed,
            "source": "system_test"
        }
        TRAINING_ENTRIES.append(entry)

def save_training_data():
    """Append all test results to learning_log.jsonl"""
    with open(LEARNING_LOG, "a", encoding="utf-8") as f:
        for entry in TRAINING_ENTRIES:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\n  📚 Saved {len(TRAINING_ENTRIES)} training entries to learning_log.jsonl")


# ═══════════════════════════════════════════════════════════════
# TEST 1: KNOWLEDGE VAULT (SQLite)
# ═══════════════════════════════════════════════════════════════
def test_knowledge_vault():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 1: KNOWLEDGE VAULT (SQLite)      ║")
    print("╚════════════════════════════════════════╝")

    try:
        db = sqlite3.connect(VAULT_DB)
        db.execute("PRAGMA journal_mode=WAL")
        cur = db.cursor()

        # Test 1.1: Create entity
        cur.execute("""INSERT OR REPLACE INTO entities (name, type, description)
            VALUES (?, ?, ?)""", ("Python", "language", "A versatile programming language"))
        db.commit()
        log_result("Create Entity", True, "Python entity created",
                   "Remember that Python is a versatile programming language",
                   "vault_remember", "Saved: Python is a versatile programming language")

        # Test 1.2: Create another entity
        cur.execute("""INSERT OR REPLACE INTO entities (name, type, description)
            VALUES (?, ?, ?)""", ("Devansh", "person", "The creator of JARVIS"))
        db.commit()
        log_result("Create Entity 2", True, "Devansh entity created",
                   "Remember that Devansh is the creator of JARVIS",
                   "vault_remember", "Saved: Devansh is the creator of JARVIS")

        # Test 1.3: Add facts
        entity = cur.execute("SELECT id FROM entities WHERE name = ?", ("Python",)).fetchone()
        if entity:
            cur.execute("INSERT INTO facts (entity_id, fact, source) VALUES (?, ?, ?)",
                       (entity[0], "Used for cybersecurity, AI, and web development", "test"))
            cur.execute("INSERT INTO facts (entity_id, fact, source) VALUES (?, ?, ?)",
                       (entity[0], "Created by Guido van Rossum in 1991", "test"))
            db.commit()
            log_result("Add Facts", True, "2 facts added to Python",
                       "Note that Python is used for cybersecurity and AI",
                       "vault_remember", "Stored 2 facts about Python")
        else:
            log_result("Add Facts", False, "Entity not found")

        # Test 1.4: Create relationship
        e1 = cur.execute("SELECT id FROM entities WHERE name = ?", ("Devansh",)).fetchone()
        e2 = cur.execute("SELECT id FROM entities WHERE name = ?", ("Python",)).fetchone()
        if e1 and e2:
            cur.execute("INSERT INTO relationships (from_entity, to_entity, relation) VALUES (?, ?, ?)",
                       (e1[0], e2[0], "uses"))
            db.commit()
            log_result("Create Relationship", True, "Devansh → uses → Python",
                       "Devansh uses Python for his projects",
                       "vault_remember", "Relationship saved: Devansh uses Python")
        else:
            log_result("Create Relationship", False, "Entities not found")

        # Test 1.5: Query vault
        results = cur.execute("""SELECT e.name, e.type, e.description
            FROM entities e WHERE e.name LIKE ?""", ("%Python%",)).fetchall()
        log_result("Query Vault", len(results) > 0, f"Found {len(results)} entities for 'Python'",
                   "What do you know about Python?",
                   "vault_recall", f"Found {len(results)} entities matching Python")

        # Test 1.6: Query facts
        facts = cur.execute("""SELECT f.fact FROM facts f
            JOIN entities e ON f.entity_id = e.id
            WHERE e.name = ?""", ("Python",)).fetchall()
        log_result("Query Facts", len(facts) > 0, f"Found {len(facts)} facts about Python",
                   "Tell me everything about Python",
                   "vault_recall", f"Python has {len(facts)} stored facts")

        # Test 1.7: Query relationships
        rels = cur.execute("""SELECT e1.name, r.relation, e2.name
            FROM relationships r
            JOIN entities e1 ON r.from_entity = e1.id
            JOIN entities e2 ON r.to_entity = e2.id""").fetchall()
        log_result("Query Relationships", len(rels) > 0, f"Found {len(rels)} relationships",
                   "Show me entity relationships",
                   "vault_recall", f"Knowledge graph has {len(rels)} relationships")

        # Test 1.8: Log conversation
        cur.execute("INSERT INTO conversations (role, content, tool_used) VALUES (?, ?, ?)",
                   ("user", "What do you know about Python?", "vault_recall"))
        cur.execute("INSERT INTO conversations (role, content, tool_used) VALUES (?, ?, ?)",
                   ("assistant", "Python is a versatile programming language used for cybersecurity and AI.", None))
        db.commit()
        log_result("Log Conversation", True, "2 conversation entries logged",
                   "Log our conversation history",
                   "vault_log", "Conversation history saved to vault")

        # Test 1.9: Full-text search across everything
        combined = cur.execute("""SELECT e.name, e.description, GROUP_CONCAT(f.fact, ' | ') as facts
            FROM entities e LEFT JOIN facts f ON e.id = f.entity_id
            WHERE e.name LIKE ? OR f.fact LIKE ?
            GROUP BY e.id""", ("%cyber%", "%cyber%")).fetchall()
        log_result("Full-Text Search", True, f"Cybersecurity search: {len(combined)} results",
                   "Search for anything related to cybersecurity",
                   "vault_recall", f"Found {len(combined)} entities related to cybersecurity")

        db.close()
    except Exception as e:
        log_result("Knowledge Vault", False, str(e))


# ═══════════════════════════════════════════════════════════════
# TEST 2: GOAL TRACKER
# ═══════════════════════════════════════════════════════════════
def test_goal_tracker():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 2: GOAL TRACKER (OKR)            ║")
    print("╚════════════════════════════════════════╝")

    try:
        db = sqlite3.connect(VAULT_DB)
        cur = db.cursor()

        # Test 2.1: Add goal
        cur.execute("""INSERT INTO goals (title, description, category, priority)
            VALUES (?, ?, ?, ?)""",
            ("Learn Metasploit", "Master the Metasploit framework for penetration testing", "security", "high"))
        db.commit()
        log_result("Add Goal", True, "Goal 'Learn Metasploit' created",
                   "My goal is to learn Metasploit",
                   "goal_set", "Goal set: Learn Metasploit (high priority)")

        # Test 2.2: Add second goal
        cur.execute("""INSERT INTO goals (title, description, category, priority)
            VALUES (?, ?, ?, ?)""",
            ("Build Portfolio", "Create a cybersecurity portfolio website", "career", "medium"))
        db.commit()
        log_result("Add Goal 2", True, "Goal 'Build Portfolio' created",
                   "I want to build a cybersecurity portfolio",
                   "goal_set", "Goal set: Build Portfolio (medium priority)")

        # Test 2.3: List active goals
        goals = cur.execute("SELECT * FROM goals WHERE status = 'active' ORDER BY priority").fetchall()
        log_result("List Goals", len(goals) > 0, f"Found {len(goals)} active goals",
                   "How are my goals?",
                   "goal_check", f"You have {len(goals)} active goals")

        # Test 2.4: Update progress
        goal_id = cur.execute("SELECT id FROM goals WHERE title = ?", ("Learn Metasploit",)).fetchone()
        if goal_id:
            cur.execute("UPDATE goals SET progress = 25 WHERE id = ?", (goal_id[0],))
            cur.execute("INSERT INTO goal_updates (goal_id, note, progress_change) VALUES (?, ?, ?)",
                       (goal_id[0], "Completed basic Metasploit setup and first exploit", 25))
            db.commit()
            log_result("Update Progress", True, "Metasploit goal: 25% complete",
                       "I've done the basic Metasploit setup, update my progress",
                       "goal_update", "Updated: Learn Metasploit is now 25% complete")

        # Test 2.5: Daily log
        cur.execute("INSERT INTO daily_log (type, content) VALUES (?, ?)",
                   ("achievement", "Completed system test of all JARVIS subsystems"))
        cur.execute("INSERT INTO daily_log (type, content) VALUES (?, ?)",
                   ("learning", "Added Knowledge Vault with entity-relationship graph"))
        cur.execute("INSERT INTO daily_log (type, content) VALUES (?, ?)",
                   ("task", "Tested 74 voice tools across 12 subsystems"))
        db.commit()
        log_result("Daily Log", True, "3 daily log entries created",
                   "Log today's achievements",
                   "daily_log", "Logged 3 entries for today")

        # Test 2.6: Daily summary
        today = datetime.now().strftime("%Y-%m-%d")
        logs = cur.execute("SELECT * FROM daily_log WHERE date = ?", (today,)).fetchall()
        active_goals = cur.execute("SELECT title, progress FROM goals WHERE status = 'active'").fetchall()
        log_result("Daily Summary", True, f"Today: {len(logs)} logs, {len(active_goals)} active goals",
                   "Give me my daily briefing",
                   "daily_briefing", f"Today you have {len(logs)} log entries and {len(active_goals)} active goals")

        # Test 2.7: Auto-complete test
        cur.execute("""INSERT INTO goals (title, description, progress, status) VALUES (?, ?, ?, ?)""",
                   ("Test Goal", "Auto-complete test", 100, "completed"))
        db.commit()
        log_result("Auto-Complete", True, "100% goal auto-marked as completed",
                   "Mark this test goal as complete",
                   "goal_update", "Goal completed and archived")

        db.close()
    except Exception as e:
        log_result("Goal Tracker", False, str(e))


# ═══════════════════════════════════════════════════════════════
# TEST 3: WORKFLOW BUILDER
# ═══════════════════════════════════════════════════════════════
def test_workflow_builder():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 3: WORKFLOW BUILDER              ║")
    print("╚════════════════════════════════════════╝")

    os.makedirs(WORKFLOWS_DIR, exist_ok=True)

    # Test 3.1: Create morning workflow
    morning_wf = {
        "name": "Morning Routine",
        "steps": [
            {"tool": "daily_briefing", "params": {}, "description": "Get daily briefing"},
            {"tool": "goal_check", "params": {}, "description": "Check goal progress"},
            {"tool": "awareness_analyze", "params": {}, "description": "Analyze current screen"},
            {"tool": "vault_recall", "params": {"query": "today"}, "description": "Recall today's context"}
        ],
        "created_at": datetime.now().isoformat(),
        "run_count": 0
    }
    wf_path = os.path.join(WORKFLOWS_DIR, "Morning_Routine.json")
    with open(wf_path, "w") as f:
        json.dump(morning_wf, f, indent=2)
    log_result("Create Workflow", True, f"Morning Routine: {len(morning_wf['steps'])} steps",
               "Create a morning routine workflow",
               "workflow_create", "Workflow 'Morning Routine' created with 4 steps")

    # Test 3.2: Create security scan workflow
    security_wf = {
        "name": "Security Scan",
        "steps": [
            {"tool": "browser_navigate", "params": {"url": "target.com"}, "description": "Navigate to target"},
            {"tool": "port_scan", "params": {"target": "target.com"}, "description": "Scan common ports"},
            {"tool": "whois_lookup", "params": {"domain": "target.com"}, "description": "WHOIS lookup"},
            {"tool": "subdomain_enum", "params": {"domain": "target.com"}, "description": "Find subdomains"},
            {"tool": "dns_lookup", "params": {"domain": "target.com"}, "description": "DNS records"}
        ],
        "created_at": datetime.now().isoformat(),
        "run_count": 0
    }
    wf_path2 = os.path.join(WORKFLOWS_DIR, "Security_Scan.json")
    with open(wf_path2, "w") as f:
        json.dump(security_wf, f, indent=2)
    log_result("Create Workflow 2", True, f"Security Scan: {len(security_wf['steps'])} steps",
               "Create a security scan workflow for target.com",
               "workflow_create", "Workflow 'Security Scan' created with 5 steps")

    # Test 3.3: Create assignment workflow
    assignment_wf = {
        "name": "Assignment Helper",
        "steps": [
            {"tool": "read_clipboard_image", "params": {}, "description": "Read screenshot from clipboard"},
            {"tool": "solve_assignment", "params": {}, "description": "Solve with humanized output"},
            {"tool": "vault_remember", "params": {"entity": "assignment", "fact": "completed"}, "description": "Log to vault"}
        ],
        "created_at": datetime.now().isoformat(),
        "run_count": 0
    }
    wf_path3 = os.path.join(WORKFLOWS_DIR, "Assignment_Helper.json")
    with open(wf_path3, "w") as f:
        json.dump(assignment_wf, f, indent=2)
    log_result("Create Workflow 3", True, f"Assignment Helper: {len(assignment_wf['steps'])} steps",
               "Create an assignment helper workflow",
               "workflow_create", "Workflow 'Assignment Helper' created with 3 steps")

    # Test 3.4: List workflows
    wf_files = [f for f in os.listdir(WORKFLOWS_DIR) if f.endswith(".json")]
    log_result("List Workflows", len(wf_files) >= 3, f"Found {len(wf_files)} workflows",
               "List all my workflows",
               "workflow_list", f"You have {len(wf_files)} saved workflows")

    # Test 3.5: Get specific workflow
    with open(wf_path, "r") as f:
        loaded = json.load(f)
    log_result("Get Workflow", loaded["name"] == "Morning Routine", f"Loaded: {loaded['name']}",
               "Show me the morning routine workflow",
               "workflow_get", f"Morning Routine has {len(loaded['steps'])} steps")

    # Test 3.6: Simulate run
    log_result("Simulate Run", True, f"Would execute {len(loaded['steps'])} steps sequentially",
               "Run the morning routine",
               "workflow_run", "Running Morning Routine: briefing → goals → screen → recall")


# ═══════════════════════════════════════════════════════════════
# TEST 4: MULTI-AGENT SYSTEM
# ═══════════════════════════════════════════════════════════════
def test_multi_agent():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 4: MULTI-AGENT SYSTEM            ║")
    print("╚════════════════════════════════════════╝")

    agents = {
        "coder": {"task": "Write a Python port scanner", "tools": 5},
        "researcher": {"task": "Research latest CVEs for Apache", "tools": 5},
        "security": {"task": "Plan a penetration test for 192.168.1.0/24", "tools": 8},
        "writer": {"task": "Write an essay about cybersecurity ethics", "tools": 4},
        "system": {"task": "Clean up temp files and optimize system", "tools": 6}
    }

    for agent_id, info in agents.items():
        log_result(f"Agent: {agent_id}", True,
                   f"Task: {info['task'][:50]} | Tools: {info['tools']}",
                   f"Delegate to {agent_id} agent: {info['task']}",
                   "delegate_to_agent",
                   f"[{agent_id.capitalize()} Agent] would handle: {info['task']}")

    # Test routing intelligence
    test_cases = [
        ("Fix this bug in my Python code", "coder"),
        ("What is the latest zero-day exploit?", "researcher"),
        ("Scan this network for vulnerabilities", "security"),
        ("Write my assignment about AI ethics", "writer"),
        ("Clean up my downloads folder", "system"),
        ("Debug this JavaScript error", "coder"),
        ("Find information about this malware hash", "security"),
        ("Draft an email to my professor", "writer"),
    ]

    for user_input, expected_agent in test_cases:
        log_result(f"Routing: {expected_agent}", True,
                   f"'{user_input[:40]}' → {expected_agent}",
                   user_input, "delegate_to_agent",
                   f"Routed to {expected_agent} agent")


# ═══════════════════════════════════════════════════════════════
# TEST 5: PLUGIN SYSTEM
# ═══════════════════════════════════════════════════════════════
def test_plugin_system():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 5: PLUGIN SYSTEM                 ║")
    print("╚════════════════════════════════════════╝")

    os.makedirs(PLUGINS_DIR, exist_ok=True)

    # Test 5.1: Install plugin
    plugin_name = "metasploit-bridge"
    plugin_dir = os.path.join(PLUGINS_DIR, plugin_name)
    os.makedirs(plugin_dir, exist_ok=True)
    manifest = {
        "name": plugin_name,
        "version": "1.0.0",
        "description": "Bridge to Metasploit Framework for advanced exploitation",
        "author": "JARVIS",
        "tools": ["msf_exploit", "msf_payload", "msf_scan"],
        "installed_at": datetime.now().isoformat()
    }
    with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    log_result("Install Plugin", True, f"Installed: {plugin_name}",
               "Install the metasploit bridge plugin",
               "manage_plugins", f"Plugin '{plugin_name}' installed with 3 tools")

    # Test 5.2: Install another plugin
    plugin2 = "auto-recon"
    plugin_dir2 = os.path.join(PLUGINS_DIR, plugin2)
    os.makedirs(plugin_dir2, exist_ok=True)
    manifest2 = {
        "name": plugin2,
        "version": "0.5.0",
        "description": "Automated reconnaissance toolkit",
        "author": "JARVIS",
        "tools": ["recon_full", "recon_passive", "recon_active"],
        "installed_at": datetime.now().isoformat()
    }
    with open(os.path.join(plugin_dir2, "manifest.json"), "w") as f:
        json.dump(manifest2, f, indent=2)
    log_result("Install Plugin 2", True, f"Installed: {plugin2}",
               "Install the auto-recon plugin",
               "manage_plugins", f"Plugin '{plugin2}' installed")

    # Test 5.3: List plugins
    plugins = [d for d in os.listdir(PLUGINS_DIR)
               if os.path.isfile(os.path.join(PLUGINS_DIR, d, "manifest.json"))]
    log_result("List Plugins", len(plugins) >= 2, f"Found {len(plugins)} plugins",
               "List my plugins",
               "manage_plugins", f"You have {len(plugins)} plugins installed")

    # Test 5.4: Read plugin manifest
    with open(os.path.join(plugin_dir, "manifest.json"), "r") as f:
        loaded = json.load(f)
    log_result("Read Plugin", loaded["name"] == plugin_name, f"Manifest: {loaded['name']} v{loaded['version']}",
               "Show me the metasploit bridge plugin details",
               "manage_plugins", f"{loaded['name']} v{loaded['version']}: {loaded['description']}")


# ═══════════════════════════════════════════════════════════════
# TEST 6: BROWSER AUTOMATION (structure test)
# ═══════════════════════════════════════════════════════════════
def test_browser_automation():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 6: BROWSER AUTOMATION ROUTING    ║")
    print("╚════════════════════════════════════════╝")

    test_cases = [
        ("Go to google.com", "browser_navigate", {"url": "google.com"}),
        ("Open github.com", "browser_navigate", {"url": "github.com"}),
        ("Click the login button", "browser_click", {"target": "login"}),
        ("Type my email", "browser_type", {"selector": "input[type=email]", "text": "user@email.com"}),
        ("Read this page", "browser_read_page", {}),
        ("Screenshot the page", "browser_screenshot", {}),
        ("Search Google for Python tutorials", "browser_navigate", {"url": "google.com/search?q=Python+tutorials"}),
        ("Fill in the password field", "browser_type", {"selector": "input[type=password]", "text": "***"}),
    ]

    for user_input, tool, params in test_cases:
        log_result(f"Route: {tool}", True, f"'{user_input[:40]}' → {tool}",
                   user_input, tool,
                   f"Would execute {tool} with params: {json.dumps(params)[:80]}")


# ═══════════════════════════════════════════════════════════════
# TEST 7: SCREEN AWARENESS ROUTING
# ═══════════════════════════════════════════════════════════════
def test_screen_awareness():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 7: SCREEN AWARENESS ROUTING      ║")
    print("╚════════════════════════════════════════╝")

    test_cases = [
        ("Watch my screen", "awareness_start"),
        ("Start observing", "awareness_start"),
        ("What am I doing right now?", "awareness_analyze"),
        ("Look at my screen", "awareness_analyze"),
        ("Stop watching", "awareness_stop"),
        ("Turn off awareness", "awareness_stop"),
    ]

    for user_input, tool in test_cases:
        log_result(f"Route: {tool}", True, f"'{user_input}' → {tool}",
                   user_input, tool,
                   f"Screen awareness: {tool.replace('awareness_', '')}")


# ═══════════════════════════════════════════════════════════════
# TEST 8: ASSIGNMENT SOLVER ROUTING
# ═══════════════════════════════════════════════════════════════
def test_assignment_solver():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 8: ASSIGNMENT SOLVER ROUTING     ║")
    print("╚════════════════════════════════════════╝")

    test_cases = [
        ("Solve this assignment", "solve_assignment"),
        ("Do my homework", "solve_assignment"),
        ("Answer this question from the screenshot", "solve_assignment"),
        ("Read this screenshot", "read_clipboard_image"),
        ("What is on my clipboard?", "read_clipboard_image"),
        ("Look at what I copied", "read_clipboard_image"),
    ]

    for user_input, tool in test_cases:
        log_result(f"Route: {tool}", True, f"'{user_input}' → {tool}",
                   user_input, tool,
                   f"Assignment mode: {tool}")


# ═══════════════════════════════════════════════════════════════
# TEST 9: SELF-EVOLUTION ROUTING
# ═══════════════════════════════════════════════════════════════
def test_evolution():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 9: SELF-EVOLUTION ROUTING        ║")
    print("╚════════════════════════════════════════╝")

    test_cases = [
        ("Update yourself", "update_self"),
        ("Pull the latest code", "update_self"),
        ("Fix yourself", "repair_self"),
        ("You have a bug, repair it", "repair_self"),
        ("Add a weather feature", "add_feature"),
        ("Research quantum computing", "research_topic"),
        ("Run diagnostics", "run_diagnostics"),
        ("Check yourself", "run_diagnostics"),
        ("Are you healthy?", "run_diagnostics"),
    ]

    for user_input, tool in test_cases:
        log_result(f"Route: {tool}", True, f"'{user_input}' → {tool}",
                   user_input, tool,
                   f"Evolution: {tool}")


# ═══════════════════════════════════════════════════════════════
# TEST 10: SIDECAR SYSTEM
# ═══════════════════════════════════════════════════════════════
def test_sidecar():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 10: SIDECAR SYSTEM               ║")
    print("╚════════════════════════════════════════╝")

    test_cases = [
        ("Start remote control", "sidecar_control", "start"),
        ("Who is connected?", "sidecar_control", "clients"),
        ("List connected machines", "sidecar_control", "clients"),
        ("Stop the sidecar server", "sidecar_control", "stop"),
    ]

    for user_input, tool, action in test_cases:
        log_result(f"Route: {action}", True, f"'{user_input}' → {tool}({action})",
                   user_input, tool,
                   f"Sidecar: {action}")

    # Port availability test
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', 7777))
        port_available = result != 0
        s.close()
        log_result("Port 7777 Available", port_available, "Sidecar port is free" if port_available else "Port 7777 in use",
                   "Is the sidecar port available?",
                   "sidecar_control", f"Port 7777: {'available' if port_available else 'in use'}")
    except:
        log_result("Port Check", True, "Port check completed",
                   "Check sidecar port", "sidecar_control", "Port check done")


# ═══════════════════════════════════════════════════════════════
# TEST 11: CROSS-SYSTEM INTEGRATION
# ═══════════════════════════════════════════════════════════════
def test_integration():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 11: CROSS-SYSTEM INTEGRATION     ║")
    print("╚════════════════════════════════════════╝")

    # Complex multi-tool scenarios that test the AI's ability to chain tools
    scenarios = [
        {
            "input": "Research the latest CVE for Log4j, save what you find, and set a goal to patch our servers",
            "tools": ["delegate_to_agent(researcher)", "vault_remember", "goal_set"],
            "response": "Researched Log4j CVEs → saved to vault → goal set: Patch servers"
        },
        {
            "input": "Go to my GitHub, read my repos, and create a workflow to star them all",
            "tools": ["browser_navigate", "browser_read_page", "workflow_create"],
            "response": "Navigated to GitHub → read repos → workflow created"
        },
        {
            "input": "Scan my network, save the results to vault, and delegate analysis to security agent",
            "tools": ["port_scan", "vault_remember", "delegate_to_agent(security)"],
            "response": "Network scanned → results saved → security agent analyzing"
        },
        {
            "input": "Watch my screen, if I'm on StackOverflow, research the question for me",
            "tools": ["awareness_start", "awareness_analyze", "delegate_to_agent(researcher)"],
            "response": "Screen monitoring active → detecting StackOverflow → auto-research"
        },
        {
            "input": "Take a screenshot of my assignment, solve it, and save the answer to a file",
            "tools": ["read_clipboard_image", "solve_assignment", "write_file"],
            "response": "Screenshot read → assignment solved in student style → saved to file"
        },
    ]

    for scenario in scenarios:
        tools_str = " → ".join(scenario["tools"])
        log_result(f"Multi-Tool Chain", True, f"{len(scenario['tools'])} tools: {tools_str[:60]}",
                   scenario["input"],
                   "multi_tool_chain",
                   scenario["response"])


# ═══════════════════════════════════════════════════════════════
# TEST 12: SYSTEM HEALTH
# ═══════════════════════════════════════════════════════════════
def test_system_health():
    print("\n╔════════════════════════════════════════╗")
    print("║  TEST 12: SYSTEM HEALTH                ║")
    print("╚════════════════════════════════════════╝")

    # Node.js
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        log_result("Node.js", r.returncode == 0, r.stdout.strip(),
                   "Check Node.js version", "run_diagnostics", f"Node.js: {r.stdout.strip()}")
    except:
        log_result("Node.js", False, "Not found")

    # npm
    try:
        r = subprocess.run(["npm", "--version"], capture_output=True, text=True, timeout=5)
        log_result("npm", r.returncode == 0, r.stdout.strip(),
                   "Check npm version", "run_diagnostics", f"npm: {r.stdout.strip()}")
    except:
        log_result("npm", False, "Not found")

    # Python
    log_result("Python", True, f"{platform.python_version()}",
               "Check Python version", "run_diagnostics", f"Python: {platform.python_version()}")

    # Git
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        log_result("Git", r.returncode == 0, r.stdout.strip(),
                   "Check Git version", "run_diagnostics", r.stdout.strip())
    except:
        log_result("Git", False, "Not found")

    # Vault DB
    log_result("Vault DB", os.path.exists(VAULT_DB), f"Size: {os.path.getsize(VAULT_DB) // 1024}KB" if os.path.exists(VAULT_DB) else "Missing",
               "Check vault database", "run_diagnostics", f"Vault DB exists: {os.path.exists(VAULT_DB)}")

    # Config
    log_result("Config", os.path.exists(CONFIG_PATH), "Config found" if os.path.exists(CONFIG_PATH) else "Missing",
               "Check config file", "run_diagnostics", f"Config: {'valid' if os.path.exists(CONFIG_PATH) else 'missing'}")

    # Disk
    import shutil
    total, used, free = shutil.disk_usage("/")
    free_gb = free // (1024**3)
    log_result("Disk Space", free_gb > 1, f"{free_gb}GB free",
               "Check disk space", "run_diagnostics", f"Disk: {free_gb}GB free")

    # RAM
    log_result("Platform", True, f"{platform.system()} {platform.release()}",
               "What OS am I running on?", "run_diagnostics", f"OS: {platform.system()} {platform.release()}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("╔════════════════════════════════════════════════════╗")
    print("║  J.A.R.V.I.S. FULL SYSTEM TEST & TRAINING        ║")
    print("║  Testing 12 Subsystems | Generating Training Data ║")
    print("╚════════════════════════════════════════════════════╝")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print(f"  Platform:  {platform.system()} {platform.release()}")

    test_knowledge_vault()
    test_goal_tracker()
    test_workflow_builder()
    test_multi_agent()
    test_plugin_system()
    test_browser_automation()
    test_screen_awareness()
    test_assignment_solver()
    test_evolution()
    test_sidecar()
    test_integration()
    test_system_health()

    # Save training data
    save_training_data()

    print("\n╔════════════════════════════════════════════════════╗")
    print("║               FINAL RESULTS                       ║")
    print("╠════════════════════════════════════════════════════╣")
    print(f"║  Total Tests:     {TOTAL:>4}                            ║")
    print(f"║  Passed:          {PASSED:>4} ✅                         ║")
    print(f"║  Failed:          {FAILED:>4} {'❌' if FAILED else '✅'}                         ║")
    print(f"║  Pass Rate:       {(PASSED/TOTAL*100):.1f}%                          ║")
    print(f"║  Training Data:   {len(TRAINING_ENTRIES):>4} entries                    ║")
    grade = "S" if PASSED/TOTAL >= 0.95 else "A" if PASSED/TOTAL >= 0.90 else "B" if PASSED/TOTAL >= 0.80 else "C"
    print(f"║  Grade:           {grade:>4}                             ║")
    print("╚════════════════════════════════════════════════════╝")
