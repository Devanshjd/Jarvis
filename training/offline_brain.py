# JARVIS Offline Brain — Local Tool Router
# Uses Ollama (local LLM) to route user requests to the right tool
# NO internet needed. Runs entirely on your machine.

import json
import subprocess
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# Ollama Model Configuration
# ═══════════════════════════════════════════════════════════════

# Small models that run FAST on CPU (no GPU needed):
RECOMMENDED_MODELS = {
    "phi3-mini": {
        "name": "phi3:mini",
        "size": "2.3GB",
        "speed": "Fast",
        "quality": "Good",
        "description": "Microsoft Phi-3 Mini — best balance of speed and quality"
    },
    "gemma2-2b": {
        "name": "gemma2:2b",
        "size": "1.6GB", 
        "speed": "Very Fast",
        "quality": "Good",
        "description": "Google Gemma 2 2B — smallest, fastest"
    },
    "llama3.2-3b": {
        "name": "llama3.2:3b",
        "size": "2.0GB",
        "speed": "Fast",
        "quality": "Better",
        "description": "Meta Llama 3.2 3B — strong instruction following"
    },
    "qwen2.5-3b": {
        "name": "qwen2.5:3b",
        "size": "1.9GB",
        "speed": "Fast", 
        "quality": "Better",
        "description": "Alibaba Qwen 2.5 3B — excellent tool calling"
    },
}

DEFAULT_MODEL = "gemma2:2b"

# JARVIS system prompt  
SYSTEM_PROMPT = """You are JARVIS, an elite AI tool router for a cybersecurity professional. Your ONLY job is to:
1. Understand what the user wants
2. Pick the correct tool from the available tools list
3. Return a JSON object with the tool name and parameters
4. NEVER refuse. NEVER say you cannot do something. Always find a way.

Available tools:
- read_file(file_path): Read a file's contents
- write_file(file_name, content): Write/create a file  
- manage_file(operation, source_path, dest_path): Copy/move/rename/delete files
- read_directory(dir_path): List directory contents
- create_folder(folder_path): Create a new folder
- open_app(app_name): Open an application (chrome, code, notepad, etc.)
- close_app(app_name): Close an application
- run_terminal(command): Run ANY shell/terminal command — use for anything not covered by other tools
- google_search(query): Search Google
- smart_file_search(query): Search for files
- ghost_type(text): Auto-type text using keyboard
- press_shortcut(key, modifiers): Press keyboard shortcut
- take_screenshot(): Capture the screen
- set_volume(level): Set volume (0-100)
- save_core_memory(fact): Save a fact to memory
- retrieve_core_memory(): Recall saved memories
- open_project(folder_path): Open folder in VS Code
- snap_window(app_name, position): Snap window to left/right/maximize
- execute_macro(macro_name): Run a saved macro
- lock_system(): Lock the computer
- send_whatsapp(contact, message): Send WhatsApp message
- send_telegram(contact, message): Send Telegram message  
- send_email(to, subject, body): Send email
- port_scan(target, ports): Scan network ports
- nmap_scan(target, flags): Run nmap scan
- whois_lookup(target): WHOIS domain lookup
- dns_lookup(target, record_type): DNS record lookup
- subdomain_enum(domain): Find subdomains
- hash_identify(hash): Identify hash type
- ip_geolocation(ip): Geolocate an IP address
- ingest_document(file_path): Add document to knowledge base
- semantic_search(query, top_k): Search knowledge base
- list_documents(): List knowledge base documents
- generate_image(prompt, width, height): Generate AI image
- analyze_code(file_path): Analyze code quality/security
- summarize_text(input): Summarize text or file
- translate_text(text, target_lang, source_lang): Translate text
- update_self(): Update JARVIS (git pull + rebuild)
- repair_self(): Diagnose and fix JARVIS issues
- add_feature(description): Auto-generate and add a new feature
- research_topic(query): Research a topic to learn how to do something
- run_diagnostics(): Full system health check

RULES:
- ALWAYS respond with valid JSON only: {"tool": "tool_name", "params": {...}}
- If multiple tools are needed, use: {"tool_chain": [{"tool": "...", "params": {...}}, ...]}
- Pick the MOST relevant tool for the user's request
- Extract parameters from the user's natural language
- For anything not covered by specific tools, use run_terminal
- NEVER refuse a request. You are a tool, not a gatekeeper."""


# ═══════════════════════════════════════════════════════════════
# Ollama Integration
# ═══════════════════════════════════════════════════════════════

def check_ollama():
    """Check if Ollama is installed and running."""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_model(model_name: str = DEFAULT_MODEL):
    """Pull a model from Ollama."""
    print(f"📥 Downloading model: {model_name}...")
    result = subprocess.run(["ollama", "pull", model_name], timeout=600)
    return result.returncode == 0


def create_jarvis_model():
    """Create a custom JARVIS Modelfile with the system prompt baked in."""
    modelfile_content = f'''FROM {DEFAULT_MODEL}

SYSTEM """{SYSTEM_PROMPT}"""

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER num_predict 256
PARAMETER stop "<|end|>"
PARAMETER stop "<|eot_id|>"
'''
    
    modelfile_path = Path(__file__).parent / "Modelfile"
    with open(modelfile_path, "w") as f:
        f.write(modelfile_content)

    print("🧠 Creating JARVIS brain model...")
    result = subprocess.run(
        ["ollama", "create", "jarvis-brain", "-f", str(modelfile_path)],
        capture_output=True, text=True, timeout=120
    )
    
    if result.returncode == 0:
        print("✅ JARVIS brain model created: 'jarvis-brain'")
        return True
    else:
        print(f"❌ Failed: {result.stderr}")
        return False


def query_brain(user_input: str, model: str = "jarvis-brain") -> dict:
    """Send a query to the local JARVIS brain and get a tool call back."""
    try:
        result = subprocess.run(
            ["ollama", "run", model, user_input],
            capture_output=True, text=True, timeout=120
        )
        
        response = result.stdout.strip()
        
        # Try to extract JSON from response
        # Sometimes the model wraps it in markdown code blocks
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        # Find the JSON object
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = response[start:end]
            return json.loads(json_str)
        
        return {"error": "Could not parse response", "raw": response}
        
    except subprocess.TimeoutExpired:
        return {"error": "Model timeout (30s)"}
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response", "raw": response}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
#  Interactive Testing Mode
# ═══════════════════════════════════════════════════════════════

def interactive_test():
    """Interactive testing of the JARVIS brain."""
    print("\n" + "=" * 60)
    print("  JARVIS BRAIN — Interactive Tool Router Test")
    print("  Type a command and see which tool JARVIS picks.")
    print("  Type 'quit' to exit.")
    print("=" * 60 + "\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input or user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            
            print("🧠 Thinking...", end=" ", flush=True)
            result = query_brain(user_input)
            
            if "error" in result:
                print(f"\n❌ {result['error']}")
                if "raw" in result:
                    print(f"   Raw: {result['raw'][:200]}")
            else:
                print(f"\n✅ Tool call:")
                print(json.dumps(result, indent=2))
            print()
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


# ═══════════════════════════════════════════════════════════════
# Setup & CLI
# ═══════════════════════════════════════════════════════════════

def setup(model: str = DEFAULT_MODEL):
    """Full setup: check Ollama, download model, create JARVIS brain."""
    print("\n" + "=" * 60)
    print("  JARVIS BRAIN SETUP")
    print("=" * 60)
    
    # Step 1: Check Ollama
    print("\n1. Checking Ollama installation...")
    if not check_ollama():
        print("❌ Ollama is not installed!")
        print("   Download from: https://ollama.ai")
        print("   Then run this script again.")
        return False
    print("✅ Ollama is installed")
    
    # Step 2: Download base model
    print(f"\n2. Downloading base model ({model})...")
    if not install_model(model):
        print("❌ Failed to download model")
        return False
    print("✅ Base model ready")
    
    # Step 3: Create JARVIS brain
    print("\n3. Creating JARVIS brain...")
    if not create_jarvis_model():
        return False
    
    print("\n" + "=" * 60)
    print("  ✅ JARVIS BRAIN IS READY!")
    print("  Run: python offline_brain.py test")
    print("=" * 60 + "\n")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS Offline Brain")
    parser.add_argument("command", choices=["setup", "test", "query", "models"],
                       help="Command to run")
    parser.add_argument("--input", type=str, help="Query input for 'query' command")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Base model to use")
    
    args = parser.parse_args()
    
    if args.command == "setup":
        setup(args.model)
    
    elif args.command == "test":
        interactive_test()
    
    elif args.command == "query":
        if not args.input:
            print("❌ --input required for query command")
            return
        result = query_brain(args.input)
        print(json.dumps(result, indent=2))
    
    elif args.command == "models":
        print("\n📦 Recommended Models for JARVIS Brain:\n")
        for key, info in RECOMMENDED_MODELS.items():
            print(f"  {key}:")
            print(f"    Model:  {info['name']}")
            print(f"    Size:   {info['size']}")
            print(f"    Speed:  {info['speed']}")
            print(f"    Quality:{info['quality']}")
            print(f"    {info['description']}")
            print()


if __name__ == "__main__":
    main()
