import os
import json
import argparse
import subprocess
import sys
import shutil
import asyncio
import inspect

from llm_processing_md.sync_md_to_json_ollama import mmd_to_json


# ── Colors helper ─────────────────────────────────────────────────────────────
class Colors:
    RED    = '\033[31m'
    GREEN  = '\033[32m'
    YELLOW = '\033[33m'
    BLUE   = '\033[34m'
    RESET  = '\033[0m'


# ── Ollama cleanup ────────────────────────────────────────────────────────────
def cleanup_ollama(model: str):
    """Stop Ollama service to free GPU memory after pipeline completes."""
    try:
        print(f"{Colors.YELLOW}Stopping Ollama to free GPU memory...{Colors.RESET}")
        result = subprocess.run(
            ["ollama", "stop", model],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"{Colors.GREEN}Ollama stopped - GPU memory freed{Colors.RESET}")
        else:
            # Try kill as fallback
            result = subprocess.run(
                ["ollama", "kill"],
                capture_output=True, text=True, timeout=30
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



# ── Resume helper ─────────────────────────────────────────────────────────────
def is_output_complete(output_dir: str, stem: str) -> bool:
    """
    Return True if all three expected output files already exist for *stem*
    inside *output_dir*.  Used to skip already-processed PDFs on resume.

    A complete run produces:
        <output_dir>/<stem>.mmd
        <output_dir>/<stem>.json
        <output_dir>/<stem>.xlsx
    """
    expected = [
        os.path.join(output_dir, f"{stem}.mmd"),
        os.path.join(output_dir, f"{stem}.json"),
    ]
    return all(os.path.isfile(p) for p in expected)


# ── Single-file pipeline ──────────────────────────────────────────────────────
def run_pipeline(input_pdf: str, output_dir: str,
                 model: str = "deepseek-r1:8b",
                 ollama_url: str = "http://localhost:11434/api/generate",
                 chunk_size: int = 2000) -> str:
    """
    End-to-end processing pipeline for a single PDF:
        PDF  →  .mmd  →  .json  →  .xlsx  (all files land in output_dir)

    Args:
        input_pdf   : path to the input PDF file
        output_dir  : directory where .mmd, .json and .xlsx will be saved
        model       : Ollama model used by mmd_to_json
        ollama_url  : Ollama API endpoint
        chunk_size  : text chunk size for LLM processing

    Returns:
        Path to the generated JSON file.
    """
    if not os.path.isfile(input_pdf):
        raise FileNotFoundError(f"PDF not found: {input_pdf}")

    os.makedirs(output_dir, exist_ok=True)

    pdf_name   = os.path.basename(input_pdf)
    stem       = os.path.splitext(pdf_name)[0]
    mmd_path   = os.path.join(output_dir, f"{stem}.mmd")
    json_path  = os.path.join(output_dir, f"{stem}.json")

    # ── Step 1: PDF → .mmd ───────────────────────────────────────────────────
    print(f"\n  [1/2] Running OCR pipeline on '{input_pdf}' …")
    try:
        subprocess.run(
            [sys.executable, "-m", "DeepSeek_OCR2_lite.run_dpsk_ocr2_pdf", input_pdf, output_dir],
            check=True,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
    except subprocess.CalledProcessError as e:
        print(f"\n  ❌ Step 1 failed with exit code {e.returncode}")
        print(f"  STDOUT:\n{e.stdout}")
        print(f"  STDERR:\n{e.stderr}")
        raise

    if not os.path.isfile(mmd_path):
        raise RuntimeError(
            f"OCR pipeline finished but expected .mmd not found: {mmd_path}"
        )
    print(f"  ✔ MMD saved → {mmd_path}")
    print(f"  {Colors.YELLOW}GPU memory freed (process ended){Colors.RESET}")

    # ── Step 2: .mmd → .json ─────────────────────────────────────────────────
    print(f"\n  [2/2] Converting MMD to JSON …")
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
    print(f"  ✔ JSON saved → {json_path}")

    if not os.path.isfile(json_path):
        raise RuntimeError(
            f"mmd_to_json finished but expected .json not found: {json_path}"
        )

    cleanup_ollama(model=model)

    return json_path


# ── Multi-file folder walker ──────────────────────────────────────────────────
def run_folder_pipeline(input_folder: str, output_root: str,
                        model: str = "deepseek-r1:8b",
                        ollama_url: str = "http://localhost:11434/api/generate",
                        chunk_size: int = 2000) -> None:
    """
    Walk *input_folder* recursively, find every .pdf, and run run_pipeline()
    on each one.

    Output layout:
        <output_root>/
            <pdf_stem_1>/
                <pdf_stem_1>.mmd
                <pdf_stem_1>.json
                <pdf_stem_1>.xlsx
            <pdf_stem_2>/
                ...

    Args:
        input_folder : root directory to search for PDF files
        output_root  : parent directory that will contain per-file sub-folders
        model        : Ollama model forwarded to run_pipeline
        ollama_url   : Ollama API endpoint forwarded to run_pipeline
        chunk_size   : chunk size forwarded to run_pipeline
    """
    if not os.path.isdir(input_folder):
        raise NotADirectoryError(f"Input folder not found: {input_folder}")

    # Collect all PDFs first so we can show a progress counter
    pdf_files = []
    for dirpath, _dirnames, filenames in os.walk(input_folder):
        for filename in filenames:
            if filename.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(dirpath, filename))

    if not pdf_files:
        print(f"{Colors.YELLOW}No PDF files found under '{input_folder}'.{Colors.RESET}")
        return

    total = len(pdf_files)
    print(f"{Colors.BLUE}Found {total} PDF file(s) under '{input_folder}'.{Colors.RESET}\n")

    succeeded, failed = [], []

    for idx, pdf_path in enumerate(pdf_files, start=1):
        stem       = os.path.splitext(os.path.basename(pdf_path))[0]
        output_dir = os.path.join(output_root, stem)

        print(f"{Colors.BLUE}{'─' * 60}{Colors.RESET}")
        print(f"{Colors.BLUE}[{idx}/{total}] Processing: {pdf_path}{Colors.RESET}")
        print(f"{Colors.BLUE}  Output dir : {output_dir}{Colors.RESET}")

        # ── Resume check ─────────────────────────────────────────────────────
        if is_output_complete(output_dir, stem):
            print(f"{Colors.YELLOW}  ⏭ Skipping (already complete): {stem}{Colors.RESET}\n")
            succeeded.append(pdf_path)
            continue

        try:
            run_pipeline(
                input_pdf  = pdf_path,
                output_dir = output_dir,
                model      = model,
                ollama_url = ollama_url,
                chunk_size = chunk_size,
            )
            print(f"{Colors.GREEN}  ✅ Done: {stem}{Colors.RESET}\n")
            succeeded.append(pdf_path)
        except Exception as exc:
            print(f"{Colors.RED}  ❌ Failed: {stem} — {exc}{Colors.RESET}\n")
            failed.append((pdf_path, str(exc)))

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"{Colors.BLUE}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.GREEN}Pipeline complete.  {len(succeeded)}/{total} file(s) succeeded.{Colors.RESET}")
    if failed:
        print(f"{Colors.RED}{len(failed)} file(s) failed:{Colors.RESET}")
        for path, err in failed:
            print(f"  • {path}\n    {err}")
    print(f"{Colors.BLUE}Outputs in: {output_root}{Colors.RESET}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="PDF → MMD → JSON → Excel pipeline (single file or whole folder)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Accept either a single PDF or a folder (mutually exclusive)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--input_pdf",    metavar="PDF",
                        help="Path to a single input PDF file")
    source.add_argument("--input_folder", metavar="DIR",
                        help="Path to a folder (searched recursively for .pdf files)")

    p.add_argument("--output_dir", default="output/",
                   help="Root directory for all outputs")
    p.add_argument("--model", default="deepseek-r1:8b",
                   help="Ollama model for MMD→JSON step")
    p.add_argument("--ollama-url", default="http://localhost:11434/api/generate",
                   help="Ollama API endpoint")
    p.add_argument("--chunk-size", default=5000, type=int,
                   help="Text chunk size for LLM processing")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()

    output_root = args.output_dir

    # NOTE: output_root is NOT wiped so that interrupted runs can be resumed.
    os.makedirs(output_root, exist_ok=True)

    if args.input_folder:
        # ── Folder mode ───────────────────────────────────────────────────────
        run_folder_pipeline(
            input_folder = args.input_folder,
            output_root  = output_root,
            model        = args.model,
            ollama_url   = args.ollama_url,
            chunk_size   = args.chunk_size,
        )
    else:
        # ── Single-file mode (backwards compatible) ───────────────────────────
        stem       = os.path.splitext(os.path.basename(args.input_pdf))[0]
        output_dir = os.path.join(output_root, stem)
        run_pipeline(
            input_pdf  = args.input_pdf,
            output_dir = output_dir,
            model      = args.model,
            ollama_url = args.ollama_url,
            chunk_size = args.chunk_size,
        )
        print(f"\n✅ Pipeline complete.  Output in: {output_dir}\n")