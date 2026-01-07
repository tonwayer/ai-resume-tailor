import json
import re
from typing import Optional, Tuple
import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)

# -------------------------
# Small utilities
# -------------------------
def _clean_ws(s: str) -> str:
    s = re.sub(r"\r", "\n", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    return _clean_ws(soup.get_text("\n"))

def _is_probably_jd(text: str) -> bool:
    t = text.lower()
    # very light heuristic; don’t overfit
    return len(text) >= 200 and (
        "responsibil" in t or "requirement" in t or "qualif" in t or "what you will do" in t
    )

# -------------------------
# ATS: Greenhouse
# URL patterns:
#  - https://boards.greenhouse.io/<company>/jobs/<id>
#  - https://boards.greenhouse.io/<company>/jobs/<id>?gh_jid=<id>
# API:
#  - https://boards-api.greenhouse.io/v1/boards/<company>/jobs/<id>
# -------------------------
def _try_greenhouse(url: str) -> Optional[str]:
    m = re.search(r"boards\.greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not m:
        # sometimes only gh_jid exists
        m2 = re.search(r"boards\.greenhouse\.io/([^/]+)/.*[?&]gh_jid=(\d+)", url)
        if not m2:
            return None
        company, job_id = m2.group(1), m2.group(2)
    else:
        company, job_id = m.group(1), m.group(2)

    api = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"
    r = SESSION.get(api, timeout=25)
    if r.status_code != 200:
        return None

    data = r.json()
    # Greenhouse description is HTML
    desc_html = data.get("content") or data.get("description") or ""
    text = _strip_html(desc_html)
    return text if _is_probably_jd(text) else None

# -------------------------
# ATS: Lever
# URL patterns:
#  - https://jobs.lever.co/<company>/<postingId>
# API:
#  - https://api.lever.co/v0/postings/<company>/<postingId>
# -------------------------
def _try_lever(url: str) -> Optional[str]:
    m = re.search(r"jobs\.lever\.co/([^/]+)/([^/?#]+)", url)
    if not m:
        return None
    company, posting_id = m.group(1), m.group(2)
    api = f"https://api.lever.co/v0/postings/{company}/{posting_id}"
    r = SESSION.get(api, timeout=25)
    if r.status_code != 200:
        return None

    data = r.json()
    # Lever fields vary; description is HTML-ish in some fields
    parts = []
    if data.get("text"):
        parts.append(_strip_html(data["text"]))
    if data.get("description"):
        parts.append(_strip_html(data["description"]))
    if data.get("additional"):
        parts.append(_strip_html(data["additional"]))

    text = _clean_ws("\n\n".join([p for p in parts if p.strip()]))
    return text if _is_probably_jd(text) else None

# -------------------------
# JSON-LD schema.org JobPosting
# -------------------------
def _extract_jobposting_jsonld(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)})
    for sc in scripts:
        raw = (sc.string or sc.get_text() or "").strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue

        # JSON-LD may be object or list
        candidates = obj if isinstance(obj, list) else [obj]
        for item in candidates:
            if not isinstance(item, dict):
                continue

            t = item.get("@type") or item.get("type")
            # sometimes nested
            if isinstance(t, list):
                t = " ".join([str(x) for x in t])

            if t and "JobPosting" in str(t):
                desc = item.get("description") or ""
                text = _strip_html(desc) if "<" in desc else _clean_ws(desc)
                if _is_probably_jd(text):
                    return text

    return None

# -------------------------
# HTML fallback (heuristics)
# -------------------------
def _extract_best_block(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # remove junk
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()

    # good candidates by id/class
    selectors = [
        "#job", "#job-description", "#job_description", "#jobDescriptionText",
        ".job", ".job-description", ".jobDescription", ".description",
        ".posting", ".posting-description", ".content", ".content-body",
        "[data-qa='job-description']",
    ]

    best_text = ""
    best_len = 0

    # try main/article first
    for container in [soup.find("main"), soup.find("article"), soup.body]:
        if not container:
            continue
        txt = _clean_ws(container.get_text("\n"))
        if len(txt) > best_len:
            best_text, best_len = txt, len(txt)

    # try targeted selectors
    for sel in selectors:
        try:
            nodes = soup.select(sel)
        except Exception:
            nodes = []
        for n in nodes:
            txt = _clean_ws(n.get_text("\n"))
            if len(txt) > best_len:
                best_text, best_len = txt, len(txt)

    # last fallback: whole page text (but cleaned)
    if best_len < 200:
        best_text = _clean_ws(soup.get_text("\n"))

    # de-duplicate repeated lines (nav)
    lines = [ln.strip() for ln in best_text.splitlines() if len(ln.strip()) >= 3]
    dedup, seen = [], set()
    for ln in lines:
        key = ln.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(ln)

    return "\n".join(dedup)

# -------------------------
# Public function
# -------------------------
def fetch_jd_text(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    # 1) ATS APIs (most reliable)
    gh = _try_greenhouse(url)
    if gh:
        return gh

    lv = _try_lever(url)
    if lv:
        return lv

    # 2) Normal HTML fetch
    r = SESSION.get(url, timeout=25, allow_redirects=True)
    if r.status_code != 200:
        raise ValueError(f"fetch failed status={r.status_code}")

    html = r.text

    # 3) JSON-LD JobPosting
    jl = _extract_jobposting_jsonld(html)
    if jl:
        return jl

    # 4) Heuristic HTML extraction
    text = _extract_best_block(html)

    if len(text) < 200:
        raise ValueError("extracted text too short (page may be JS-rendered).")

    return text
