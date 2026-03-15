# JEE_rankup_OCR Docker Image
# Base: CUDA 12.1 with cuDNN 8 for GPU support

FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV VLLM_USE_V1=0
ENV CUDA_VISIBLE_DEVICES=0
ENV OLLAMA_HOST=http://localhost:11434
# HuggingFace cache directory - models stored here
ENV HF_HOME=/models
ENV MODEL_PATH=deepseek-ai/DeepSeek-OCR-2

# Install system dependencies
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    python3-pip \
    git \
    wget \
    curl \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create Python 3.12 symlinks
RUN ln -sf /usr/bin/python3.12 /usr/bin/python && \
    ln -sf /usr/bin/python3.12 /usr/bin/python3

# install uv
RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Upgrade pip and install basic tools
RUN uv pip install --system --upgrade pip setuptools wheel

# Install PyTorch with CUDA 12.1 support
RUN uv pip install --system torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu118

# Install vLLM (pre-built wheel for CUDA 12.1)
RUN uv pip install --system https://github.com/vllm-project/vllm/releases/download/v0.8.5/vllm-0.8.5+cu121-cp38-abi3-manylinux1_x86_64.whl

# Install project requirements
COPY requirements.txt /tmp/requirements.txt
RUN uv pip install --system -r /tmp/requirements.txt

# Install flash-attn (required for DeepSeek-OCR-2)
RUN uv pip install --system flash-attn==2.7.3 --no-build-isolation

# Create app directory and models directory
WORKDIR /app
RUN mkdir -p /models

# Copy project files (excluding .venv, .git, etc.)
COPY . /app/

# Download DeepSeek-OCR-2 model at build time
RUN python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('${MODEL_PATH}', trust_remote_code=True)"

# Default command - keep container running for interactive use
CMD ["tail", "-f", "/dev/null"]
