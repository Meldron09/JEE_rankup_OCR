import os
import json
import argparse
import subprocess
import sys
import shutil
import asyncio
import inspect

import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv

from llm_processing_md.async_md_to_json_ollama import mmd_to_json
from utils.dynamodb_utils import update_task_completed
from utils.s3_utils import upload_folder, download_file
from utils.helpers import Colors, get_ollama_url, cleanup_ollama

load_dotenv()

# ── Core pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(
    input_pdf:  str,
    output_dir: str,
    model:      str = "deepseek-r1:8b",
    ollama_url: str = None,
    chunk_size: int = 3000,
) -> str:
    """
    End-to-end processing pipeline:
        PDF  →  .mmd  →  .json   (all files land in output_dir)

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

    if ollama_url is None:
        ollama_url = get_ollama_url()
        print(f"Using Ollama URL: {ollama_url}")

    pdf_name  = os.path.basename(input_pdf)
    stem      = os.path.splitext(pdf_name)[0]
    mmd_path  = os.path.join(output_dir, f"{stem}.mmd")
    json_path = os.path.join(output_dir, f"{stem}.json")

    # ── Step 1: PDF → .mmd ───────────────────────────────────────────────────
    print(f"\n[1/2] Running OCR pipeline on '{input_pdf}' …")
    try:
        subprocess.run(
            [sys.executable, "-m", "DeepSeek_OCR2_lite.run_dpsk_ocr2_pdf", input_pdf, output_dir],
            check=True,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),
        )
    except subprocess.CalledProcessError as e:
        print(f"\n{Colors.RED}❌ Step 1 failed with exit code {e.returncode}{Colors.RESET}")
        print(f"STDOUT:\n{e.stdout}")
        print(f"STDERR:\n{e.stderr}")
        raise

    if not os.path.isfile(mmd_path):
        raise RuntimeError(f"OCR pipeline finished but expected .mmd not found: {mmd_path}")

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
    if inspect.isawaitable(result):
        asyncio.run(result)
    print(f"✔ JSON saved → {json_path}")

    cleanup_ollama(model=model)

    print(f"\n✅ Pipeline complete.  Outputs in: {output_dir}\n")
    return json_path


# ── S3-aware entry-point ──────────────────────────────────────────────────────

def run_s3_pipeline(
    bucket: str,
    s3_input_key: str,
    table_name: str,
    task_id: str,
    s3_output_prefix: str = "output",
    model:      str = "deepseek-r1:8b",
    ollama_url: str = None,
    chunk_size: int = 3000,
):
    """
    Full S3-aware pipeline:
        1. Download PDF from S3  →  input/<filename>
        2. Run processing pipeline  →  output/<stem>/
        3. Upload output/<stem>/  →  S3 under <s3_output_prefix>/<stem>/
        4. Delete local input/ and output/ directories

    Args:
        s3_input_key    : Full S3 key of the source PDF (e.g. "input/report.pdf")
        s3_output_prefix: S3 key prefix for uploaded outputs (default: "output")
        table_name      : Name of the DynamoDB table
        task_id         : Task ID from the DynamoDB table
        model           : Ollama model for MMD→JSON step
        ollama_url      : Ollama API endpoint (auto-detected if None)
        chunk_size      : Text chunk size for LLM processing
    """
    if not bucket:
        raise EnvironmentError("S3_BUCKET environment variable is not set.")

    # Derive local paths
    pdf_filename = os.path.basename(s3_input_key)          # e.g. "report.pdf"
    stem         = os.path.splitext(pdf_filename)[0]        # e.g. "report"

    input_dir    = "input"
    local_pdf    = os.path.join(input_dir, pdf_filename)    # input/report.pdf
    output_root  = "output"
    output_dir   = os.path.join(output_root, stem)          # output/report/

    # ── Clean slate ──────────────────────────────────────────────────────────
    for directory in (input_dir, output_root):
        if os.path.exists(directory):
            shutil.rmtree(directory)

    os.makedirs(input_dir,  exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    try:
        # ── Step 1: Download from S3 ─────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"  S3 Download: s3://{bucket}/{s3_input_key}")
        print(f"{'='*60}")
        download_file(bucket=bucket, object_key=s3_input_key, local_path=local_pdf)

        # ── Step 2: Run processing pipeline ─────────────────────────────────
        print(f"\n{'='*60}")
        print(f"  Processing: {local_pdf}")
        print(f"  Output dir: {output_dir}")
        print(f"{'='*60}")
        run_pipeline(
            input_pdf=local_pdf,
            output_dir=output_dir,
            model=model,
            ollama_url=ollama_url,
            chunk_size=chunk_size,
        )

        # ── Step 3: Upload outputs to S3 ─────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"  Uploading: {output_dir} -> s3://{bucket}/{s3_output_prefix}/{stem}/")
        print(f"{'='*60}")
        upload_folder(
            bucket=bucket,
            s3_prefix=s3_output_prefix,
            local_folder=output_dir,
        )

        # ── Step 4: Mark task as COMPLETED in DynamoDB ───────────────────────
        output_s3_key = f"{s3_output_prefix}/{stem}"
        update_task_completed(table_name=table_name, task_id=task_id, output_s3_key=output_s3_key)
 
        print(f"\n{Colors.GREEN}✅ S3 pipeline complete for '{pdf_filename}'.{Colors.RESET}")

    finally:
        # ── Step 4: Clean up local directories (always runs) ─────────────────
        print(f"\n{Colors.YELLOW}Cleaning up local directories...{Colors.RESET}")
        for directory in (input_dir, output_root):
            if os.path.exists(directory):
                shutil.rmtree(directory)
                print(f"{Colors.YELLOW}Removed: {directory}/{Colors.RESET}")



if __name__ == "__main__":
    bucket = os.getenv("S3_BUCKET",None)
    table_name = os.getenv("DYNAMODB_TABLE",None)
    task_id = os.getenv("TASK_ID",None)
    s3_input_key = os.getenv("S3_KEY",None)
    model=os.getenv("LLM_MODEL",None)

    print(f"Bucket: {bucket}")
    print(f"Task ID: {task_id}")
    print(f"S3 Input Key: {s3_input_key}")
    print(f"Model: {model}")
    print(f"Table Name: {table_name}")

    if s3_input_key:
        # ── S3 mode ───────────────────────────────────────────────────────────
        print('Running S3 mode')
        run_s3_pipeline(
            bucket=bucket,
            s3_input_key=s3_input_key,
            table_name=table_name,
            task_id=task_id,
            model=model,
        )
    else:
        print('Running non-S3 mode')
        input_pdf="/home/cmengi/Desktop/test/optimized_ocr/JEE_rankup_OCR/input/original-1-3.pdf"
        output_dir="output"
        shutil.rmtree(output_dir)
        run_pipeline(
            input_pdf=input_pdf,
            output_dir=output_dir,
            model=model,
        )
