import requests
import json
from langchain_text_splitters import RecursiveCharacterTextSplitter
from json_repair import repair_json
from .prompt import PROMPT


def mmd_to_json(mmd_path: str, output_json_path: str,
                model: str = "deepseek-r1:8b",
                ollama_url: str = "http://localhost:11434/api/generate",
                chunk_size: int = 3000):
    """
    Convert a .mmd OCR output file into structured JSON using an LLM.

    Args:
        mmd_path (str): path to the input .mmd file
        output_json_path (str): path where JSON will be saved
        model (str): Ollama model name
        ollama_url (str): Ollama API endpoint
        chunk_size (int): text chunk size for LLM processing
    """

    # Load MMD file
    with open(mmd_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into logical chunks (questions)
    splitter = RecursiveCharacterTextSplitter(
        separators=[r"\n(?=\d+\.\s)"],
        keep_separator=True,
        is_separator_regex=True,
        chunk_size=chunk_size,
        chunk_overlap=0,
    )

    chunks = splitter.split_text(content)

    final_response = []

    for chunk in chunks:

        payload = {
            "model": model,
            "prompt": PROMPT.format(CHUNK_CONTENT=chunk),
            "stream": False
        }

        try:
            response = requests.post(ollama_url, json=payload)
            
            result = response.json()["response"]

            # clean formatting
            result = result.strip().replace("```json", "").replace("```", "")

            # repair malformed json
            parsed = json.loads(repair_json(result))

            if isinstance(parsed, list):
                final_response.extend(parsed)
            else:
                final_response.append(parsed)

        except Exception as e:
            print(f"Error processing chunk: {e}")
            raise Exception(f"Error processing chunk: {e}")

    # Save JSON
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(final_response, f, indent=2, ensure_ascii=False)

    print(f"\nSaved JSON to: {output_json_path}")

    return final_response