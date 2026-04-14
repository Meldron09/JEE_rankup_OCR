import asyncio
import aiohttp
import json
from langchain_text_splitters import RecursiveCharacterTextSplitter
from json_repair import repair_json
from .prompt import PROOF_READING_PROMPT, PROMPT
import asyncio
from langchain_core.documents import Document

def process_markdown_to_chunks(mmd_path, chunk_size=1000):
    # 1. Read the raw content
    with open(mmd_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 2. Initial Split by Page Tag
    pages = content.split("<--- Page Split --->")
    
    # 3. Define your specialized Question Splitter
    # The separator r"\n(?=\d+\.\s)" splits before a newline followed by a digit and a dot
    splitter = RecursiveCharacterTextSplitter(
        separators=[r"\n(?=\d+\.\s)"], 
        keep_separator=True,
        is_separator_regex=True,
        chunk_size=chunk_size,
        chunk_overlap=0,
    )

    final_chunks = []

    for i, page_text in enumerate(pages):
        clean_page = page_text.strip()
        if not clean_page:
            continue
            
        # 4. Split the page content into individual question chunks
        # We use .split_text() on the string content of the page
        question_texts = splitter.split_text(clean_page)
        
        for chunk_text in question_texts:
            # 5. Create Document objects with combined metadata
            doc = Document(
                page_content=chunk_text.strip(),
                metadata={
                    "source": mmd_path,
                    "page_number": i + 1,
                }
            )
            final_chunks.append(doc)
    
    return final_chunks

async def process_chunk(session, chunk, model, ollama_url, semaphore):
    async with semaphore:
        prompt = PROOF_READING_PROMPT.replace("{page_number}", str(chunk.metadata.get("page_number")))
        prompt = prompt.replace("{content}", chunk.page_content)
        payload = {
            "model": model,
            "prompt": prompt,
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
    model: str = "ministral-3:14b-cloud",
    ollama_url: str = "http://localhost:11434/api/generate",
    chunk_size: int = 3000,
    concurrency: int = 5
):
    print('Model name',model)
    
    chunks = process_markdown_to_chunks(mmd_path)

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
    asyncio.run(mmd_to_json("/home/meldron/Desktop/PP/JEE_rankup_OCR/original-1-3.mmd", 
    "/home/meldron/Desktop/PP/JEE_rankup_OCR/new_output_original-1-3.json"))



