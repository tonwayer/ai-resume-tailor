import os
import ast
import json
import requests


from fastapi import HTTPException
from dotenv import load_dotenv


load_dotenv()


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-chat"

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"

def ollama_chat(system: str, user: str, temperature: float = 0.0, model: str | None = None) -> str:
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

def deepseek_chat(system: str, user: str, temperature: float = 0.0) -> str:
    if not DEEPSEEK_API_KEY:
        raise HTTPException(500, "DeepSeek API key not configured")
    print("calling deepseek")
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }

    r = requests.post(
        DEEPSEEK_URL,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    if r.status_code != 200:
        raise HTTPException(500, f"DeepSeek error: {r.text}")

    data = r.json()
    return data["choices"][0]["message"]["content"]

def llm_chat(provider: str,
        system: str,
        user: str,
        temperature: float = 0.0,
        model: str | None = None
    ) -> str:
    if provider == "deepseek":
        return deepseek_chat(system, user, temperature=temperature, model=model)
    return ollama_chat(system, user, temperature=temperature, model=model)
