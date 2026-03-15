# JEE_rankup_OCR

A PDF OCR pipeline for processing JEE (Joint Entrance Examination) physics exam papers. Converts PDF documents to structured JSON with question parsing.

## Pipeline

```
PDF → DeepSeek-OCR-2 (vLLM) → .mmd → Ollama (LLM) → structured JSON
```

## Features

- PDF to Markdown conversion using DeepSeek-OCR-2 with vLLM inference
- Intelligent image tiling for high-resolution exam papers
- Automatic question parsing using LLM (Ollama)
- Structured JSON output with question numbers, images, options, answers, and solutions
- Web interface via Streamlit

## Requirements

### Hardware
- NVIDIA GPU with CUDA 11.8+
- 16GB+ GPU memory recommended

### Software
- Python 3.12.9
- [vLLM](https://docs.vllm.ai/) for efficient inference
- [Ollama](https://ollama.com/) running locally with deepseek-r1:8b

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/JEE_rankup_OCR.git
cd JEE_rankup_OCR
```

2. **Create virtual environment:**
```bash
uv venv --python=3.12.9
source .venv/bin/activate
```

3. **Download vLLM wheel:**
Download `vllm-0.8.5+cu121-cp38-abi3-manylinux1_x86_64.whl` from the [vLLM releases](https://github.com/vllm-project/vllm/releases/tag/v0.8.5) page.

4. **Install PyTorch:**
```bash
uv pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu118
```

5. **Install vLLM:**
```bash
uv pip install vllm-0.8.5+cu121-cp38-abi3-manylinux1_x86_64.whl
```

6. **Install other dependencies:**
```bash
uv pip install -r requirements.txt
```

7. **Install flash-attn:**
```bash
uv pip install flash-attn==2.7.3 --no-build-isolation
```

8. **Set up Ollama:**
```bash
# Install Ollama and pull the model
ollama pull deepseek-r1:8b
```

## Configuration

Edit `DeepSeek_OCR2_lite/config.py` to configure:

| Parameter | Description |
|-----------|-------------|
| `MODEL_PATH` | Path to DeepSeek-OCR-2 weights |
| `CROP_MODE` | Enable dynamic image tiling for high-resolution PDFs |
| `MAX_CONCURRENCY` | GPU batch size |
| `NUM_WORKERS` | Image preprocessing threads |

## Usage

### Command Line

Run the full pipeline:
```bash
python main.py <input_pdf> --output_dir <output_dir> --model deepseek-r1:8b
```

Example:
```bash
python main.py sample.pdf --output_dir ./output --model deepseek-r1:8b
```

View help:
```bash
python main.py --help
```

### Batch Processing (main_walk.py)

For batch processing multiple PDFs or folder processing with resume support:

**Single PDF:**
```bash
python main_walk.py --input_pdf sample.pdf --output_dir ./output
```

**Process folder recursively:**
```bash
python main_walk.py --input_folder ./pdfs --output_dir ./output
```

**With custom model:**
```bash
python main_walk.py --input_folder ./pdfs --output_dir ./output --model deepseek-r1:8b
```

**With custom chunk size:**
```bash
python main_walk.py --input_pdf sample.pdf --output_dir ./output --chunk-size 3000
```

**Features:**
- **Resume support**: Skips already-processed files if output exists
- **GPU memory cleanup**: Automatically stops Ollama after processing to free GPU memory
- **Output structure**: `<output_dir>/<pdf_name>/<pdf_name>.mmd` and `<pdf_name>.json`

View help:
```bash
python main_walk.py --help
```

### Programmatic Usage

**OCR only (PDF → .mmd):**
```python
from DeepSeek_OCR2_lite.run_dpsk_ocr2_pdf import run_ocr_pipeline

run_ocr_pipeline("input.pdf", "output_dir/")
```

**LLM conversion only (.mmd → JSON):**
```python
from llm_processing_md.md_to_json_ollama import mmd_to_json

mmd_to_json("input.mmd", "output.json", model="deepseek-r1:8b")
```

### Web Interface

Launch the Streamlit web app:
```bash
streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

## Output Format

The pipeline produces structured JSON with the following schema:

```json
{
  "questions": [
    {
      "question_number": 1,
      "question": "Question text...",
      "images": ["image_data_or_path"],
      "options": {
        "A": "Option A text",
        "B": "Option B text",
        "C": "Option C text",
        "D": "Option D text"
      },
      "answer": "A",
      "solution": "Step-by-step solution..."
    }
  ]
}
```

## Project Structure

```
JEE_rankup_OCR/
├── main.py                          # Entry point
├── streamlit_app.py                 # Web interface
├── requirements.txt                 # Python dependencies
├── README.md                        # This file
├── CLAUDE.md                        # Developer documentation
├── DeepSeek_OCR2_lite/
│   ├── config.py                   # Model configuration
│   ├── run_dpsk_ocr2_pdf.py        # PDF to MMD conversion
│   ├── deepseek_ocr2.py            # Model definition
│   ├── deepencoderv2/              # Custom vision encoder
│   └── process/                    # Image preprocessing
└── llm_processing_md/
    ├── md_to_json_ollama.py         # MMD to JSON conversion
    └── prompt.py                    # LLM prompt template
```

## Troubleshooting

### GPU Out of Memory
Reduce `MAX_CONCURRENCY` in `config.py`:
```python
MAX_CONCURRENCY = 4  # Lower from 10
```

### Ollama Connection Error
Ensure Ollama is running:
```bash
ollama serve
```

### Model Not Found
Set the model path in `config.py`:
```python
MODEL_PATH = '/path/to/your/model'
```

## License

MIT License

## Acknowledgments

- [DeepSeek-OCR-2](https://github.com/deepseek-ai/DeepSeek-OCR-2) for the OCR model
- [vLLM](https://github.com/vllm-project/vllm) for efficient inference
- [Ollama](https://ollama.com/) for local LLM hosting