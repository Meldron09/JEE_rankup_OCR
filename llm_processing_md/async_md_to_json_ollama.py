import asyncio
import aiohttp
import json
from langchain_text_splitters import RecursiveCharacterTextSplitter
from json_repair import repair_json
from .prompt import PROMPT
import asyncio

async def process_chunk(session, chunk, model, ollama_url, semaphore):
    async with semaphore:
        payload = {
            "model": model,
            "prompt": PROMPT.format(CHUNK_CONTENT=chunk),
            "stream": False
        }

        try:
            async with session.post(ollama_url, json=payload) as response:
                data = await response.json()
                result = data["response"]

                result = result.strip().replace("```json", "").replace("```", "")

                parsed = json.loads(repair_json(result))

                if isinstance(parsed, list):
                    return parsed
                else:
                    return [parsed]

        except Exception as e:
            print(f"Error processing chunk: {e}")
            raise Exception(f"Error processing chunk: {e}")


async def mmd_to_json(
    mmd_path: str,
    output_json_path: str,
    model: str = "qwen3.5:397b-cloud",
    ollama_url: str = "http://localhost:11434/api/generate",
    chunk_size: int = 3000,
    concurrency: int = 5
):
    print('Model name',model)
    # Load file
    with open(mmd_path, "r", encoding="utf-8") as f:
        content = f.read()

    splitter = RecursiveCharacterTextSplitter(
        separators=[r"\n(?=\d+\.\s)"],
        keep_separator=True,
        is_separator_regex=True,
        chunk_size=chunk_size,
        chunk_overlap=0,
    )

    chunks = splitter.split_text(content)

    semaphore = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession() as session:

        tasks = [
            process_chunk(session, chunk, model, ollama_url, semaphore)
            for chunk in chunks
        ]

        results = await asyncio.gather(*tasks)

    final_response = []

    for r in results:
        final_response.extend(r)

    # Save JSON
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(final_response, f, indent=2, ensure_ascii=False)

    print(f"\nSaved JSON to: {output_json_path}")

    return final_response

if __name__ == "__main__":
    asyncio.run(mmd_to_json("/home/cmengi/Desktop/test/optimized_ocr/JEE_rankup_OCR/original-1-3.mmd", 
    "/home/cmengi/Desktop/test/optimized_ocr/JEE_rankup_OCR/output/original-1-3.json"))



