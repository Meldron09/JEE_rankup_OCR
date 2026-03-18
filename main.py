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
from dynamodb_utils import update_task_completed

load_dotenv()


# ── S3 client setup ───────────────────────────────────────────────────────────

s3 = boto3.client(
    service_name="s3",
    region_name=os.getenv("AWS_DEFAULT_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)


# ── S3 helpers ────────────────────────────────────────────────────────────────

def upload_folder(bucket: str, s3_prefix: str, local_folder: str):
    """
    Upload an entire local folder to S3.

    The S3 key for each file will be:
        <s3_prefix>/<base_folder_name>/<relative_path_inside_folder>

    Args:
        bucket       : S3 bucket name
        s3_prefix    : Key prefix inside the bucket (e.g. "output")
        local_folder : Local directory to upload
    """
    base_folder = os.path.basename(os.path.normpath(local_folder))

    for root, dirs, files in os.walk(local_folder):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, local_folder)
            s3_key = os.path.join(s3_prefix, base_folder, relative_path).replace("\\", "/")

            try:
                s3.upload_file(local_path, bucket, s3_key)
                print(f"{Colors.GREEN}Uploaded:{Colors.RESET} {local_path} -> s3://{bucket}/{s3_key}")
            except Exception as e:
                print(f"{Colors.RED}Failed to upload {local_path}: {e}{Colors.RESET}")


def download_file(bucket: str, object_key: str, local_path: str):
    """
    Download a single file from S3 to a local path.

    Args:
        bucket     : S3 bucket name
        object_key : Full S3 key of the object (e.g. "input/report.pdf")
        local_path : Destination path on local disk
    """
    try:
        s3.download_file(Bucket=bucket, Key=object_key, Filename=local_path)
        print(f"{Colors.GREEN}Downloaded:{Colors.RESET} s3://{bucket}/{object_key} -> {local_path}")
    except FileNotFoundError:
        print(f"{Colors.RED}Destination path is invalid: {local_path}{Colors.RESET}")
        raise
    except NoCredentialsError:
        print(f"{Colors.RED}AWS credentials not available.{Colors.RESET}")
        raise
    except ClientError as e:
        print(f"{Colors.RED}S3 download failed: {e}{Colors.RESET}")
        raise


# ── Ollama helpers ────────────────────────────────────────────────────────────

def get_ollama_url() -> str:
    """
    Get Ollama URL from environment variable or use default.
    Constructs the full API endpoint from OLLAMA_HOST.
    """
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    base_url = ollama_host.rstrip("/")
    return f"{base_url}/api/generate"


class Colors:
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    BLUE   = "\033[34m"
    RESET  = "\033[0m"


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
        s3_output_prefix : S3 key prefix for uploaded outputs (default: "output")
        model            : Ollama model for MMD→JSON step
        ollama_url       : Ollama API endpoint (auto-detected if None)
        chunk_size       : Text chunk size for LLM processing
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

        print(f"\n{Colors.GREEN}✅ S3 pipeline complete for '{pdf_filename}'.{Colors.RESET}")

        # ── Step 4: Mark task as COMPLETED in DynamoDB ───────────────────────
        output_s3_key = f"{s3_output_prefix}/{stem}"
        update_task_completed(output_s3_key=output_s3_key)
 
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
        run_s3_pipeline(
            bucket=bucket,
            s3_input_key=s3_input_key,
            model=model,
        )
    else:
        input_pdf="/home/cmengi/Desktop/test/optimized_ocr/JEE_rankup_OCR/input/original-1-3.pdf"
        output_dir="output"
        run_pipeline(
            input_pdf=input_pdf,
            output_dir=output_dir,
            model=model,
        )
        shutil.rmtree(output_dir)