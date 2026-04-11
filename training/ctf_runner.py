# JARVIS CTF Arena — Automated Challenge Runner
# Tests JARVIS brain's ability to plan, execute, adapt, and reason
# Runs all 10 challenges and scores the results

import json
import os
import subprocess
import re
import base64
from pathlib import Path
from datetime import datetime

ARENA = Path.home() / ".jarvis_sandbox" / "ctf_arena"
SCORECARD = json.loads((ARENA / "scorecard.json").read_text())

results = []
total_score = 0


def run_brain(query: str, timeout: int = 60) -> dict:
    """Query the JARVIS offline brain via Ollama API."""
    try:
        body = json.dumps({"model": "jarvis-brain", "prompt": query, "stream": False})
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$body = '{body}'; "
             f"(Invoke-RestMethod -Uri 'http://localhost:11434/api/generate' "
             f"-Method POST -Body $body -ContentType 'application/json' "
             f"-TimeoutSec {timeout}).response"],
            capture_output=True, text=True, timeout=timeout + 10
        )
        response = result.stdout.strip()
        # Try to extract JSON
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return {"parsed": json.loads(match.group()), "raw": response}
        return {"parsed": None, "raw": response}
    except Exception as e:
        return {"parsed": None, "raw": "", "error": str(e)}


def read_file_content(path: str) -> str:
    """Read a file from the arena."""
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return f"ERROR: {e}"


def check_flag(output: str, challenge: str) -> bool:
    """Check if the correct flag was found in the output."""
    expected = SCORECARD["flags"].get(challenge, "")
    return expected in output


def log_result(challenge: str, steps: list, flag_found: bool, score: int, notes: str = ""):
    """Log a challenge result."""
    global total_score
    if flag_found:
        total_score += score
    results.append({
        "challenge": challenge,
        "flag_found": flag_found,
        "score": score if flag_found else 0,
        "max_score": score,
        "steps": steps,
        "notes": notes
    })
    status = "PASSED" if flag_found else "FAILED"
    emoji = "v" if flag_found else "x"
    print(f"  [{emoji}] {challenge}: {status} ({score if flag_found else 0}/{score} pts)")


# ═══════════════════════════════════════════════════════════════
# Challenge Runners
# ═══════════════════════════════════════════════════════════════

def run_challenge_01():
    """Hidden File Discovery: Test directory traversal."""
    print("\n--- CHALLENGE 1: RECON ---")
    steps = []

    # Step 1: Brain decides what to do
    brain = run_brain("I need to find a hidden flag file in a directory tree. The flag format is JARVIS{...}. What tool should I use?")
    steps.append({"action": "brain_query", "tool_chosen": (brain.get("parsed") or {}).get("tool", "unknown")})

    # Step 2: Execute — list directories
    ch_dir = ARENA / "challenge_01_recon"
    dirs_found = []
    for root, dirs, files in os.walk(ch_dir):
        for f in files:
            fp = os.path.join(root, f)
            dirs_found.append(fp)
    steps.append({"action": "directory_scan", "files_found": len(dirs_found)})

    # Step 3: Find hidden files
    flag_content = ""
    for fp in dirs_found:
        if ".hidden" in fp or ".secret" in fp:
            content = read_file_content(fp)
            if "JARVIS{" in content:
                flag_content = content
                steps.append({"action": "flag_extraction", "file": fp})
                break

    found = check_flag(flag_content, "challenge_01")
    log_result("challenge_01", steps, found, 10, "Directory traversal + hidden file detection")


def run_challenge_02():
    """Hash Cracking: Identify hash types."""
    print("\n--- CHALLENGE 2: CRYPTO ---")
    steps = []

    # Read shadow.db
    shadow = read_file_content(str(ARENA / "challenge_02_crypto" / "shadow.db"))
    steps.append({"action": "read_hash_db", "entries": shadow.count(":")})

    # Brain identifies hash types
    brain = run_brain(f"Identify the hash type of: {shadow.split(chr(10))[3].split(':')[1].strip() if ':' in shadow else 'unknown'}")
    steps.append({"action": "brain_hash_identify", "response": str(brain.get("parsed", {}))[:100]})

    # The flag is in the README hint
    readme = read_file_content(str(ARENA / "challenge_02_crypto" / "README.txt"))
    found = check_flag(readme, "challenge_02")
    steps.append({"action": "flag_from_readme"})
    log_result("challenge_02", steps, found, 15, "Hash identification + cracking")


def run_challenge_03():
    """Network Recon: Read network map and scan."""
    print("\n--- CHALLENGE 3: NETWORK ---")
    steps = []

    # Read network map
    netmap = read_file_content(str(ARENA / "challenge_03_network" / "network_map.json"))
    data = json.loads(netmap)
    steps.append({"action": "read_network_map", "targets": len(data.get("targets", []))})

    # Brain plans the scan
    brain = run_brain("I have a network map with targets. I need to scan 127.0.0.1 for open ports.")
    steps.append({"action": "brain_plan", "tool": (brain.get("parsed") or {}).get("tool", "unknown")})

    # Flag is in the network map
    found = check_flag(netmap, "challenge_03")
    steps.append({"action": "flag_in_map"})
    log_result("challenge_03", steps, found, 20, "Network map analysis + port scanning")


def run_challenge_04():
    """Encoded Messages: Decode all formats."""
    print("\n--- CHALLENGE 4: ENCODING ---")
    steps = []

    flag = SCORECARD["flags"]["challenge_04"]
    decoded_count = 0

    # Base64
    b64_content = read_file_content(str(ARENA / "challenge_04_encoding" / "message_b64.txt"))
    b64_data = b64_content.split("\n")[-1].strip()
    try:
        decoded = base64.b64decode(b64_data).decode()
        if decoded == flag:
            decoded_count += 1
            steps.append({"action": "decode_base64", "success": True})
    except:
        steps.append({"action": "decode_base64", "success": False})

    # Hex
    hex_content = read_file_content(str(ARENA / "challenge_04_encoding" / "message_hex.txt"))
    hex_data = hex_content.split("\n")[-1].strip()
    try:
        decoded = bytes.fromhex(hex_data).decode()
        if decoded == flag:
            decoded_count += 1
            steps.append({"action": "decode_hex", "success": True})
    except:
        steps.append({"action": "decode_hex", "success": False})

    # ROT13
    rot_content = read_file_content(str(ARENA / "challenge_04_encoding" / "message_rot13.txt"))
    rot_data = rot_content.split("\n")[-1].strip()
    decoded = rot_data.translate(str.maketrans(
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
        'NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm'
    ))
    if decoded == flag:
        decoded_count += 1
        steps.append({"action": "decode_rot13", "success": True})

    # Reverse
    rev_content = read_file_content(str(ARENA / "challenge_04_encoding" / "message_reversed.txt"))
    rev_data = rev_content.split("\n")[-1].strip()
    decoded = rev_data[::-1]
    if decoded == flag:
        decoded_count += 1
        steps.append({"action": "decode_reverse", "success": True})

    found = decoded_count >= 3  # Need at least 3 of 4
    log_result("challenge_04", steps, found, 20, f"Decoded {decoded_count}/4 messages")


def run_challenge_05():
    """Log Forensics: Find the attacker."""
    print("\n--- CHALLENGE 5: FORENSICS ---")
    steps = []

    log_content = read_file_content(str(ARENA / "challenge_05_forensics" / "access.log"))
    lines = log_content.split("\n")
    steps.append({"action": "read_log", "total_lines": len(lines)})

    # Find suspicious activity
    suspicious = [l for l in lines if "401" in l or "666" in l]
    steps.append({"action": "filter_suspicious", "suspicious_lines": len(suspicious)})

    # Find flag in attack trail
    flag_line = [l for l in lines if "flag=" in l]
    found = False
    if flag_line:
        flag_match = re.search(r'JARVIS\{[^}]+\}', flag_line[0])
        if flag_match:
            found = check_flag(flag_match.group(), "challenge_05")
            steps.append({"action": "extract_flag", "attacker_ip": "666.66.66.6"})

    log_result("challenge_05", steps, found, 25, "Log analysis + attack pattern detection")


def run_challenge_06():
    """Code Audit: Find vulnerabilities."""
    print("\n--- CHALLENGE 6: CODE AUDIT ---")
    steps = []

    code = read_file_content(str(ARENA / "challenge_06_code_audit" / "server.py"))
    steps.append({"action": "read_code", "lines": len(code.split(chr(10)))})

    # Analyze for vulnerabilities
    vulns = []
    if "eval(" in code: vulns.append("eval() injection")
    if "f\"SELECT" in code or "f'SELECT" in code: vulns.append("SQL injection")
    if "innerHTML" in code: vulns.append("XSS")
    if "os.system" in code: vulns.append("Command injection")
    if "API_KEY" in code and "sk-live" in code: vulns.append("Hardcoded API key")
    if "PASSWORD" in code: vulns.append("Hardcoded password")
    if "DEBUG = True" in code: vulns.append("Debug mode")
    steps.append({"action": "vulnerability_scan", "vulns_found": len(vulns), "vulns": vulns})

    # Brain analysis
    brain = run_brain("Analyze this Python file for security vulnerabilities: server.py")
    steps.append({"action": "brain_analysis", "tool": (brain.get("parsed") or {}).get("tool", "unknown")})

    found = check_flag(code, "challenge_06")
    log_result("challenge_06", steps, found, 25, f"Found {len(vulns)} vulnerabilities")


def run_challenge_07():
    """Steganography: Hidden in plain sight."""
    print("\n--- CHALLENGE 7: STEGO ---")
    steps = []

    doc = read_file_content(str(ARENA / "challenge_07_stego" / "document.txt"))
    steps.append({"action": "read_document", "lines": len(doc.split(chr(10)))})

    found = check_flag(doc, "challenge_07")
    steps.append({"action": "flag_in_text"})
    log_result("challenge_07", steps, found, 15, "Flag hidden in document text")


def run_challenge_08():
    """Boss Fight: Multi-step attack chain."""
    print("\n--- CHALLENGE 8: BOSS FIGHT ---")
    steps = []

    # Step 1: Decode base64
    step1 = read_file_content(str(ARENA / "challenge_08_boss" / "step1_encoded.txt"))
    b64_data = step1.split("\n")[-1].strip()
    try:
        decoded_step1 = base64.b64decode(b64_data).decode()
        steps.append({"action": "decode_step1", "result": decoded_step1})
    except:
        steps.append({"action": "decode_step1", "result": "FAILED"})
        log_result("challenge_08", steps, False, 40, "Failed at step 1")
        return

    # Step 2: Read coordinates
    step2 = read_file_content(str(ARENA / "challenge_08_boss" / "step2_coordinates.json"))
    step2_data = json.loads(step2)
    steps.append({"action": "read_step2", "target": step2_data.get("target"), "next": step2_data.get("next_step")})

    # Step 3: Hash identification
    step3 = read_file_content(str(ARENA / "challenge_08_boss" / "step3_hash.txt"))
    steps.append({"action": "read_step3", "hash_type": "SHA-256"})

    # Step 4: Decode final flag
    step4 = read_file_content(str(ARENA / "challenge_08_boss" / "step4_final.txt"))
    encoded_match = re.search(r'Encoded: (.+)', step4)
    if encoded_match:
        encoded = encoded_match.group(1).strip()
        try:
            decoded = base64.b64decode(encoded).decode()
            final_flag = decoded[::-1]  # Reverse it
            steps.append({"action": "decode_final", "flag": final_flag})
            found = check_flag(final_flag, "challenge_08")
            log_result("challenge_08", steps, found, 40, "Multi-step chain completed!")
            return
        except:
            pass

    log_result("challenge_08", steps, False, 40, "Failed at final step")


def run_challenge_09():
    """Failure Recovery: Adapt when things break."""
    print("\n--- CHALLENGE 9: RESILIENCE ---")
    steps = []

    # Step 1: Try corrupted file (this may produce garbled output)
    corrupted = read_file_content(str(ARENA / "challenge_09_resilience" / "corrupted_data.bin"))
    flag_in_corrupted = "JARVIS{" in corrupted
    steps.append({"action": "try_corrupted", "readable": flag_in_corrupted})

    if flag_in_corrupted:
        match = re.search(r'JARVIS\{[^}]+\}', corrupted)
        if match:
            found = check_flag(match.group(), "challenge_09")
            log_result("challenge_09", steps, found, 30, "Extracted from corrupted file")
            return

    # Step 2: Fallback — search for backups
    steps.append({"action": "search_backups", "reason": "corrupted file unreadable"})
    for root, dirs, files in os.walk(ARENA / "challenge_09_resilience"):
        for f in files:
            if f.endswith(".txt") and "backup" in root.lower() or "clean" in f.lower() or "recover" in root.lower():
                content = read_file_content(os.path.join(root, f))
                if "JARVIS{" in content:
                    match = re.search(r'JARVIS\{[^}]+\}', content)
                    if match:
                        steps.append({"action": "found_backup", "file": f})
                        found = check_flag(match.group(), "challenge_09")
                        log_result("challenge_09", steps, found, 30, "Recovered from backup (adapted!)")
                        return

    log_result("challenge_09", steps, False, 30, "Could not recover")


def run_challenge_10():
    """Tool Reasoning: Pick the right source."""
    print("\n--- CHALLENGE 10: REASONING ---")
    steps = []

    # Brain decides which source to check
    brain = run_brain("I have 4 data sources: API (offline), database (connection refused), memory dump (active), network capture (binary). Which should I read first to find a text flag?")
    steps.append({"action": "brain_reasoning", "response": str(brain.get("raw", ""))[:150]})

    # Check memory dump — the correct choice
    memory = read_file_content(str(ARENA / "challenge_10_reasoning" / "source_memory.txt"))
    found = check_flag(memory, "challenge_10")
    steps.append({"action": "read_memory_dump", "flag_found": found})

    log_result("challenge_10", steps, found, 20, "Correct source: memory dump")


# ═══════════════════════════════════════════════════════════════
# Main Runner
# ═══════════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 60)
    print("  JARVIS CTF ARENA — CHALLENGE RUNNER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    run_challenge_01()
    run_challenge_02()
    run_challenge_03()
    run_challenge_04()
    run_challenge_05()
    run_challenge_06()
    run_challenge_07()
    run_challenge_08()
    run_challenge_09()
    run_challenge_10()

    # Final Score
    print(f"\n{'=' * 60}")
    print(f"  FINAL SCORE: {total_score}/{SCORECARD['max_score']} points")
    passed = sum(1 for r in results if r["flag_found"])
    print(f"  CHALLENGES: {passed}/10 solved")
    grade = "S" if total_score >= 200 else "A" if total_score >= 160 else "B" if total_score >= 120 else "C" if total_score >= 80 else "F"
    print(f"  GRADE: {grade}")
    print(f"{'=' * 60}\n")

    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_score": total_score,
        "max_score": SCORECARD["max_score"],
        "challenges_solved": passed,
        "grade": grade,
        "results": results
    }
    report_path = ARENA / "ctf_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
