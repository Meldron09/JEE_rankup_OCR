"""
Streamlit UI for PDF OCR Pipeline
Run PDF → .mmd → .json → .xlsx with a web interface

GPU Optimizations (mirroring main.py):
  - Step 1 (PDF → .mmd) runs in an isolated subprocess so GPU memory is freed
    when the OCR process exits, before Step 2 begins.
  - After Step 2 (.mmd → .json), Ollama is stopped via `ollama stop <model>`
    (with `ollama kill` as fallback) to release VRAM before Step 3.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import streamlit as st
import inspect

from llm_processing_md.sync_md_to_json_ollama import mmd_to_json

import asyncio

# Page configuration
st.set_page_config(
    page_title="JEE OCR Pipeline",
    page_icon="📄",
    layout="wide"
)

# Default output directory
DEFAULT_OUTPUT_DIR = "output"


# ── GPU / process helpers (ported from main.py) ───────────────────────────────

def run_ocr_subprocess(input_pdf: str, output_dir: str) -> subprocess.CompletedProcess:
    """
    Run the OCR step in an isolated subprocess so GPU memory is freed
    as soon as the child process exits (mirrors main.py Step 1).
    """
    return subprocess.run(
        [sys.executable, "-m", "DeepSeek_OCR2_lite.run_dpsk_ocr2_pdf", input_pdf, output_dir],
        check=True,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )


def cleanup_ollama(model: str):
    """
    Stop Ollama to free GPU memory after the LLM step completes.
    Tries `ollama stop <model>` first, then `ollama kill` as a fallback.
    Mirrors main.py's cleanup_ollama().
    """
    try:
        result = subprocess.run(
            ["ollama", "stop", model],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            st.info("🟡 Ollama stopped — GPU memory freed.")
        else:
            # Fallback: kill
            result = subprocess.run(
                ["ollama", "kill"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                st.info("🟡 Ollama killed — GPU memory freed.")
            else:
                st.warning(f"Ollama stop warning: {result.stderr}")
    except FileNotFoundError:
        st.warning("Ollama CLI not found — skipping GPU cleanup.")
    except subprocess.TimeoutExpired:
        st.warning("Ollama stop timed out.")
    except Exception as e:
        st.warning(f"Ollama cleanup error: {e}")


# ── Utility helpers ───────────────────────────────────────────────────────────

def delete_output_folder(output_dir: str):
    """Delete output folder if it exists."""
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
        st.info(f"Deleted existing output folder: {output_dir}")


def zip_output_folder(output_dir: str) -> bytes:
    """Zip the entire output folder and return as bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in sorted(files):
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zf.write(file_path, arcname)
    buf.seek(0)
    return buf.getvalue()


def display_output_files(output_dir: str):
    """Display output folder contents with per-file download buttons."""
    if not os.path.exists(output_dir):
        st.warning("Output folder does not exist.")
        return

    all_files = []
    for root, dirs, files in os.walk(output_dir):
        for file in sorted(files):
            all_files.append(os.path.join(root, file))

    if not all_files:
        st.warning("Output folder is empty.")
        return

    st.subheader("📁 Output Files")

    # ── FIX: cache zip bytes in session_state so the download URL stays valid
    #    across Streamlit reruns triggered by the button click itself.
    zip_name = f"{os.path.basename(output_dir)}.zip"
    zip_cache_key = f"zip_cache_{output_dir}"
    if zip_cache_key not in st.session_state:
        st.session_state[zip_cache_key] = zip_output_folder(output_dir)

    st.download_button(
        label="⬇️ Download All (ZIP)",
        data=st.session_state[zip_cache_key],
        file_name=zip_name,
        mime="application/zip",
        key="download_all_zip"
    )

    st.divider()

    for file_path in sorted(all_files):
        file_size = os.path.getsize(file_path)
        display_name = os.path.relpath(file_path, output_dir)

        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"

        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"📄 **{display_name}** ({size_str})")
        with col2:
            with open(file_path, "rb") as f:
                st.download_button(
                    label="Download",
                    data=f.read(),
                    file_name=os.path.basename(file_path),
                    key=f"download_{display_name}"
                )


# ── Pipeline runners ──────────────────────────────────────────────────────────

def run_ocr_only(input_pdf: str, output_dir: str, original_name: str):
    """
    Run only the OCR step: PDF → .mmd
    Step runs in an isolated subprocess (GPU freed on exit).
    """
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(original_name)[0]
    mmd_path = os.path.join(output_dir, f"{stem}.mmd")

    st.info(f"[1/1] Running OCR pipeline on '{original_name}' (subprocess)…")
    try:
        proc = run_ocr_subprocess(input_pdf, output_dir)
    except subprocess.CalledProcessError as e:
        st.error(f"OCR subprocess failed (exit {e.returncode})")
        if e.stdout:
            st.code(e.stdout, language="text")
        if e.stderr:
            st.code(e.stderr, language="text")
        raise RuntimeError("OCR step failed — see details above.")

    st.info("🟡 OCR subprocess completed — GPU memory freed.")

    if os.path.isfile(mmd_path):
        st.success(f"✔ MMD saved → {mmd_path}")
        return mmd_path
    else:
        raise RuntimeError(f"OCR pipeline finished but expected .mmd not found: {mmd_path}")


def run_full_pipeline(
    input_pdf: str,
    output_dir: str,
    original_name: str,
    model: str = "deepseek-r1:8b",
    ollama_url: str = "http://localhost:11434/api/generate",
    chunk_size: int = 2000
):
    """
    Run the full pipeline: PDF → .mmd → .json → .xlsx

    GPU optimizations (matching main.py):
      1. OCR (Step 1) runs in an isolated subprocess → GPU freed on process exit.
      2. cleanup_ollama() called after Step 2 → VRAM released before Step 3.
    """
    os.makedirs(output_dir, exist_ok=True)

    stem       = os.path.splitext(original_name)[0]
    mmd_path   = os.path.join(output_dir, f"{stem}.mmd")
    json_path  = os.path.join(output_dir, f"{stem}.json")

    # ── Step 1: PDF → .mmd  (isolated subprocess) ────────────────────────────
    st.info(f"[1/2] Running OCR pipeline on '{original_name}' (subprocess)…")
    try:
        proc = run_ocr_subprocess(input_pdf, output_dir)
    except subprocess.CalledProcessError as e:
        st.error(f"OCR subprocess failed (exit {e.returncode})")
        if e.stdout:
            st.code(e.stdout, language="text")
        if e.stderr:
            st.code(e.stderr, language="text")
        raise RuntimeError("OCR step failed — see details above.")

    # Child process has exited → GPU memory freed
    st.info("🟡 OCR subprocess completed — GPU memory freed.")

    if not os.path.isfile(mmd_path):
        raise RuntimeError(f"OCR pipeline finished but expected .mmd not found: {mmd_path}")
    st.success(f"✔ MMD saved → {mmd_path}")

    # ── Step 2: .mmd → .json ─────────────────────────────────────────────────
    st.info("[2/2] Converting MMD to JSON…")
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
    st.success(f"✔ JSON saved → {json_path}")

    # Stop Ollama to free GPU memory before Step 3
    st.info("🟡 Stopping Ollama to free GPU memory…")
    cleanup_ollama(model=model)

    return json_path


# ── Streamlit UI ──────────────────────────────────────────────────────────────

def main():
    st.title("📄 JEE OCR Pipeline")
    st.markdown(
        "Upload a PDF and choose between **OCR Only** or **Full Pipeline** processing.\n\n"
    )

    # Sidebar settings
    st.sidebar.header("⚙️ Settings")

    model = st.sidebar.selectbox(
        "Ollama Model",
        ["deepseek-r1:8b","ministral-3:14b-cloud"],
        index=0,
    )

    output_dir = st.sidebar.text_input("Output Directory", value=DEFAULT_OUTPUT_DIR)

    # File uploader
    uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])

    # Processing option
    option = st.radio(
        "Processing Option",
        ["OCR Only (PDF → .mmd)", "Full Pipeline (PDF → .mmd → .json → .xlsx)"],
        horizontal=True,
    )

    # Run button
    if st.button("🚀 Run", type="primary", disabled=uploaded_file is None):
        if uploaded_file is None:
            st.error("Please upload a PDF file first.")
            return

        # Clear any stale zip cache from a previous run
        for k in list(st.session_state.keys()):
            if k.startswith("zip_cache_"):
                del st.session_state[k]

        # Save uploaded file to a temp dir under its original filename
        tmp_dir = tempfile.mkdtemp()
        input_pdf = os.path.join(tmp_dir, uploaded_file.name)
        with open(input_pdf, "wb") as f:
            f.write(uploaded_file.getvalue())

        try:
            delete_output_folder(output_dir)

            with st.container():
                if option == "OCR Only (PDF → .mmd)":
                    run_ocr_only(input_pdf, output_dir, original_name=uploaded_file.name)
                    st.balloons()
                    st.success("✅ OCR Only completed!")
                else:
                    run_full_pipeline(
                        input_pdf,
                        output_dir,
                        original_name=uploaded_file.name,
                        model=model,
                        ollama_url="http://localhost:11434/api/generate",
                        chunk_size=5000
                    )

                    st.balloons()
                    st.success("✅ Full Pipeline completed!")

            st.divider()
            display_output_files(output_dir)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    main()