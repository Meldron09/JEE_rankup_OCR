# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a PDF OCR pipeline for processing JEE (Joint Entrance Examination) physics exam papers. It converts PDF documents → Markdown (.mmd) → Structured JSON with question parsing.

**Pipeline flow:**
```
PDF → DeepSeek-OCR-2 (vLLM) → .mmd → Ollama (LLM) → structured JSON
```

## Commands

### Run the full pipeline
```bash
python main.py <input_pdf> --output_dir <output_dir> --model deepseek-r1:8b
```

### Run only OCR (PDF → .mmd)
```python
from DeepSeek_OCR2_lite.run_dpsk_ocr2_pdf import run_ocr_pipeline
run_ocr_pipeline("input.pdf", "output_dir/")
```

### Run only LLM conversion (.mmd → JSON)
```python
from llm_processing_md.md_to_json_ollama import mmd_to_json
mmd_to_json("input.mmd", "output.json", model="deepseek-r1:8b")
```

## Architecture

### main.py
Entry point that orchestrates the full pipeline.

### DeepSeek_OCR2_lite/
- **run_dpsk_ocr2_pdf.py**: PDF→MMD conversion using vLLM inference with DeepSeek-OCR-2 model
- **deepseek_ocr2.py**: vLLM-compatible model definition (MultiModalProcessor + causal LM)
- **config.py**: Model path, prompts, concurrency settings. Edit `MODEL_PATH` to use local weights
- **deepencoderv2/**: Custom vision encoder (SAM + Qwen2 decoder as encoder + MLP projector)
- **process/**: Image preprocessing (cropping, tiling) and ngram logits processing

### llm_processing_md/
- **md_to_json_ollama.py**: Splits .mmd into question chunks and converts to JSON using Ollama API
- **prompt.py**: LLM prompt that parses exam questions into structured JSON (question_number, question, images, options, answer, solution)

## Requirements

- DeepSeek-OCR-2 model weights (deepseek-ai/DeepSeek-OCR-2)
- Ollama running locally with deepseek-r1:8b (or custom model)
- CUDA 11.8+ with GPU
- Python dependencies: vllm, torch, transformers, pymupdf, pillow, langchain-text-splitters, json-repair

## Configuration

Edit `DeepSeek_OCR2_lite/config.py`:
- `MODEL_PATH`: Path to DeepSeek-OCR-2 weights
- `CROP_MODE`: Enable dynamic image tiling for high-resolution PDFs
- `MAX_CONCURRENCY`: GPU batch size
- `NUM_WORKERS`: Image preprocessing threads
