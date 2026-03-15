BASE_SIZE = 1024
IMAGE_SIZE = 768
CROP_MODE = True
MIN_CROPS= 2
MAX_CROPS= 6 # max:6
MAX_CONCURRENCY = 10 # If you have limited GPU memory, lower the concurrency count.
NUM_WORKERS = 16 # image pre-process (resize/padding) workers 
PRINT_NUM_VIS_TOKENS = False
SKIP_REPEAT = True
MODEL_PATH = 'deepseek-ai/DeepSeek-OCR-2' # change to your model path

# Input/output paths should be passed via command line arguments or environment
# .pdf: run_dpsk_ocr_pdf.py
# .jpg, .png, .jpeg: run_dpsk_ocr_image.py
# Omnidocbench images path: run_dpsk_ocr_eval_batch.py

PROMPT = '<image>\n<|grounding|>Convert the document to markdown.'
# PROMPT = '<image>\nFree OCR.'
# .......


from transformers import AutoTokenizer

TOKENIZER = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
