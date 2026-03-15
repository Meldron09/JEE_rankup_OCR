import os
import json
import argparse
import subprocess
import sys
import shutil
import asyncio
import inspect

from llm_processing_md.sync_md_to_json_ollama import mmd_to_json

def run_pipeline(input_pdf: str, output_dir: str,
                 model: str = "deepseek-r1:8b",
                 ollama_url: str = "http://localhost:11434/api/generate",
                 chunk_size: int = 2000) -> str:
    """
    End-to-end processing pipeline:
        PDF  →  .mmd  →  .json   (all files land in output_dir)

    Uses subprocess isolation to ensure GPU memory is freed between steps.

    Args:
        input_pdf   : path to the input PDF file
        output_dir  : directory where .mmd and .json will be saved
        model       : Ollama model used by mmd_to_json
        ollama_url  : Ollama API endpoint
        chunk_size  : text chunk size for LLM processing

    Returns:
        Path to the generated JSON file.
    """
    if not os.path.isfile(input_pdf):
        raise FileNotFoundError(f"PDF not found: {input_pdf}")

    os.makedirs(output_dir, exist_ok=True)

    pdf_name   = os.path.basename(input_pdf)          # e.g. "report.pdf"
    stem       = os.path.splitext(pdf_name)[0]        # e.g. "report"
    mmd_path   = os.path.join(output_dir, f"{stem}.mmd")
    json_path  = os.path.join(output_dir, f"{stem}.json")

    # ── Step 1: PDF → .mmd (runs in subprocess to free GPU after) ────────────
    print(f"\n[1/2] Running OCR pipeline on '{input_pdf}' …")

    step1_script = os.path.join(os.path.dirname(__file__), "DeepSeek_OCR2_lite", "run_dpsk_ocr2_pdf.py")

    try:
        step1_result = subprocess.run(
            [sys.executable, "-m", "DeepSeek_OCR2_lite.run_dpsk_ocr2_pdf", input_pdf, output_dir],
            check=True,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__)  # ensure correct working directory
        )

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Step 1 failed with exit code {e.returncode}")
        print(f"STDOUT:\n{e.stdout}")
        print(f"STDERR:\n{e.stderr}")
        raise
    if not os.path.isfile(mmd_path):
        raise RuntimeError(
            f"OCR pipeline finished but expected .mmd not found: {mmd_path}"
        )
    print(f"✔ MMD saved → {mmd_path}")
    print(f"{Colors.YELLOW}GPU memory freed (process ended){Colors.RESET}")

    # ── Step 2: .mmd → .json ─────────────────────────────────────────────────
    print(f"\n[2/2] Converting MMD to JSON …")
    result = mmd_to_json(
        mmd_path=mmd_path,
        output_json_path=json_path,
        model=model,
        ollama_url=ollama_url,
        chunk_size=chunk_size,
    )
    # Handle both async and sync implementations of mmd_to_json
    if inspect.isawaitable(result):
        asyncio.run(result)
    print(f"✔ JSON saved → {json_path}")

    cleanup_ollama(model=model)

    print(f"\n✅ Pipeline complete.  Outputs in: {output_dir}\n")
    return json_path


# Add Colors class for use in main.py
class Colors:
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    RESET = '\033[0m'

def cleanup_ollama(model: str):                                                                                                          
    """                                                                                                                               
    Stop Ollama service to free GPU memory after pipeline completes.                                                                
    Uses 'ollama kill' to terminate the running Ollama process.                                                                
    """                                                                                                                        
    try:                                                                                                                       
        print(f"{Colors.YELLOW}Stopping Ollama to free GPU memory...{Colors.RESET}")                                           
        result = subprocess.run(                                                                                               
            ["ollama", "stop",model],                                                                                                
            capture_output=True,                                                                                               
            text=True,                                                                                                         
            timeout=30                                                                                                         
        )                                                                                                                      
        if result.returncode == 0:                                                                                             
            print(f"{Colors.GREEN}Ollama stopped - GPU memory freed{Colors.RESET}")                                            
        else:                                                                                                                  
            # Try kill as fallback                                                                                             
            result = subprocess.run(                                                                                           
                ["ollama", "kill"],                                                                                            
                capture_output=True,                                                                                           
                text=True,                                                                                                     
                timeout=30                                                                                                     
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
                                                                                                                               

# ── CLI entry-point ───────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="PDF → MMD → JSON processing pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input_pdf",help="Path to the input PDF")
    p.add_argument("--output_dir", default="output/",help="Directory for all outputs")
    p.add_argument("--model",default="deepseek-r1:8b",
                   help="Ollama model for MMD→JSON step")
    # p.add_argument("--model",default="deepseek-r1:1.5b",
    #                help="Ollama model for MMD→JSON step")
    p.add_argument("--ollama-url", default="http://localhost:11434/api/generate",
                   help="Ollama API endpoint")
    p.add_argument("--chunk-size", default=3000, type=int,
                   help="Text chunk size for LLM processing")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    
    output_dir = "output"
    # Delete output folder if it exists``
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    
    run_pipeline(
        input_pdf  = args.input_pdf,
        output_dir = args.output_dir,
        model      = args.model,
        ollama_url = args.ollama_url,
        chunk_size = args.chunk_size,
    )