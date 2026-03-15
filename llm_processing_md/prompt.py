PROMPT = """
You are an expert physics exam content parser.

You will be given the extracted markdown/text content of a CHUNK of a competitive exam paper.

Important context about the chunk:
- The chunk may contain MULTIPLE questions.
- Questions may not be sequential.
- Each chunk may contain several questions and you must detect and process EVERY question present in the chunk. Do NOT skip any questions.
- OCR noise may be present.
- LaTeX expressions may be present.
- Image placeholders like <!-- image --> may appear.
- Questions themselves may contain images.
- Answer options may ALSO contain images.
- Mixed formatting may exist.
- Separate "Ans:" and "Sol:" sections may appear anywhere in the chunk.
- Answer keys or solutions may be written elsewhere within the chunk.

Your task is to:

1. Identify EACH complete question within the chunk.
2. A question is considered COMPLETE only if:
   - It contains question text
   - It contains answer options
   - It contains a correct answer
   - It contains a solution
3. If ANY of the following is missing for a question:
   - Options
   - Answer
   - Solution
   → IGNORE that question completely.
4. For each valid complete question, extract and return structured JSON with the following keys:

- "question_number": integer
- "question": full cleaned question text (preserve equations in LaTeX if present)
- "images": array of strings (include ALL image tags (for ex - ![](images/1_1.jpg)) exactly as they appear for that question, in order of appearance; if no images are present, return an empty array [])
- "options": array of strings (each option exactly as written, cleaned; options themselves may contain image tags and those should be preserved exactly)
- "answer": correct option (return option number)
- "solution": full worked solution text (cleaned and readable)

Important Rules:

- Every valid question will ALWAYS contain options, answer, and solution.
- If any one of these three components is missing, DO NOT include that question in output.
- Carefully scan the entire chunk to ensure no questions are skipped.
- Consider only image tags (for ex - ![](images/1_1.jpg)) that appear within that specific question block.
- If images appear inside options, preserve them exactly within the option text.
- If multiple image tags appear consecutively under a question, consider all of them.
- Do NOT hallucinate or infer missing data.
- Clean obvious OCR artifacts but do not change scientific meaning.
- Preserve equations in LaTeX format wherever possible.
- Return STRICTLY VALID JSON.
- Do NOT include explanations outside JSON.
- If multiple valid questions exist in the chunk, return a JSON array.
- If no complete valid questions are found, return an empty JSON array: [].

Output format example:

[
  {{
    "question_number": 26,
    "question": "10 kg of ice at -10°C is added to 100 kg of water at 25°C...",
    "images": ["![](images/0_0.jpg)", "![](images/1_1.jpg)"],
    "options": [
      "10",
      "15",
      "6.67",
      "11.6"
    ],
    "answer": "(1)",
    "solution": "Using heat balance equation..."
  }}
]

Now parse the following chunk content:

{CHUNK_CONTENT}

"""