import os
import subprocess

class Colors:
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    BLUE   = "\033[34m"
    RESET  = "\033[0m"

# ── Ollama helpers ────────────────────────────────────────────────────────────

def get_ollama_url() -> str:
    """
    Get Ollama URL from environment variable or use default.
    Constructs the full API endpoint from OLLAMA_HOST.
    """
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    base_url = ollama_host.rstrip("/")
    return f"{base_url}/api/generate"


def cleanup_ollama(model: str):
    """Stop Ollama service to free GPU memory after pipeline completes."""
    try:
        print(f"{Colors.YELLOW}Stopping Ollama to free GPU memory...{Colors.RESET}")
        result = subprocess.run(
            ["ollama", "stop", model],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"{Colors.GREEN}Ollama stopped - GPU memory freed{Colors.RESET}")
        else:
            result = subprocess.run(
                ["ollama", "kill"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                print(f"{Colors.GREEN}Ollama killed - GPU memory freed{Colors.RESET}")
            else:
                print(f"{Colors.YELLOW}Ollama stop warning: {result.stderr}{Colors.RESET}")
    except FileNotFoundError:
        print(f"{Colors.YELLOW}Ollama CLI not found - skipping cleanup{Colors.RESET}")
    except subprocess.TimeoutExpired:
        print(f"{Colors.YELLOW}Ollama stop timed out{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.YELLOW}Ollama cleanup error: {e}{Colors.RESET}")
