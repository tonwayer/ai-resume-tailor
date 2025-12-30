import re
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def extract_visible_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body
    text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")

    lines = [clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if len(line) >= 3]

    dedup, seen = [], set()
    for line in lines:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(line)

    return "\n".join(dedup)

def fetch_jd_text(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    if r.status_code != 200:
        raise ValueError(f"fetch failed status={r.status_code}")
    jd_text = extract_visible_text_from_html(r.text)
    if len(jd_text) < 200:
        raise ValueError("extracted text too short")
    return jd_text
