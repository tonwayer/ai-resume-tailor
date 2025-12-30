import ast
import json
import requests
from fastapi import HTTPException

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"

def ollama_chat(system: str, user: str, temperature: float = 0.0) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": temperature},
        "stream": False,
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=180)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Ollama error: {r.text}")

    return r.json()["message"]["content"]

def extract_json_strict(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model did not return a JSON object.")

    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        parsed = ast.literal_eval(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("Model did not return a JSON object.")
        return parsed
