import os
import time
import json
from typing import Dict, Any, List

import requests
import xml.etree.ElementTree as ET

from fastmcp import FastMCP

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

# 推奨: 自分のメールにする（NCBIのリクエスト識別用）
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "your_email@example.com")
NCBI_TOOL = os.getenv("NCBI_TOOL", "chatgpt-pubmed-mcp")

# 任意: NCBI API Key（なくても動く）
NCBI_API_KEY = os.getenv("NCBI_API_KEY")

mcp = FastMCP(from starlette.responses import PlainTextResponsefrom starlette.requests import Request
from starlette.responses import PlainTextResponse

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


@mcp.custom_route("/health", methods=["GET", "HEAD"])
async def health_check(request):
    return PlainTextResponse("ok")

    name="PubMed MCP",
    instructions="Search PubMed and fetch abstracts by PMID via NCBI E-utilities.",
)


def _throttle() -> None:
    # NCBI推奨の負荷を超えないよう、控えめに間引き
    time.sleep(0.4)


def _get_json(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    _throttle()
    p = dict(params)
    p.update({"tool": NCBI_TOOL, "email": NCBI_EMAIL, "retmode": "json"})
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY

    r = requests.get(BASE + path, params=p, timeout=30)
    r.raise_for_status()
    return r.json()


def _get_xml(path: str, params: Dict[str, Any]) -> str:
    _throttle()
    p = dict(params)
    p.update({"tool": NCBI_TOOL, "email": NCBI_EMAIL, "retmode": "xml"})
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY

    r = requests.get(BASE + path, params=p, timeout=30)
    r.raise_for_status()
    return r.text


@mcp.tool()
def search(query: str, retmax: int = 20) -> Dict[str, List[Dict[str, Any]]]:
    """
    PubMed検索（ESearch→ESummary）
    Returns: {"results":[{"id","title","text","url","metadata"}...]}
    """
    q = (query or "").strip()
    if not q:
        return {"results": []}

    es = _get_json(
        "esearch.fcgi",
        {"db": "pubmed", "term": q, "retmax": int(retmax)},
    )
    ids = es.get("esearchresult", {}).get("idlist", []) or []
    if not ids:
        return {"results": []}

    sm = _get_json("esummary.fcgi", {"db": "pubmed", "id": ",".join(ids)})

    out: List[Dict[str, Any]] = []
    for pmid in ids:
        item = (sm.get("result", {}) or {}).get(pmid, {}) or {}
        title = (item.get("title") or "").strip()
        journal = item.get("fulljournalname") or item.get("source") or ""
        pubdate = item.get("pubdate") or ""
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        out.append(
            {
                "id": pmid,
                "title": title or f"PMID:{pmid}",
                "text": " / ".join([s for s in [journal, pubdate] if s]),
                "url": url,
                "metadata": {"journal": journal, "pubdate": pubdate},
            }
        )

    return {"results": out}


@mcp.tool()
def fetch(pmid: str) -> Dict[str, Any]:
    """
    PMIDから詳細取得（EFetch）
    Returns: {"content":[{"type":"text","text":"<json>"}]}
    """
    pid = (pmid or "").strip()
    if not pid:
        raise ValueError("pmid is required")

    xml_text = _get_xml("efetch.fcgi", {"db": "pubmed", "id": pid})
    root = ET.fromstring(xml_text)

    def first_text(path: str) -> str:
        el = root.find(path)
        return (el.text or "").strip() if el is not None else ""

    title = first_text(".//ArticleTitle")
    journal = first_text(".//Journal/Title")
    year = first_text(".//PubDate/Year") or first_text(".//ArticleDate/Year")

    abstract_parts: List[str] = []
    for a in root.findall(".//Abstract/AbstractText"):
        if a.text:
            abstract_parts.append(a.text.strip())
    abstract = "\n".join(abstract_parts).strip()

    doc = {
        "id": pid,
        "title": title or f"PMID:{pid}",
        "text": f"{journal} ({year})\n\n{abstract}".strip(),
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
        "metadata": {"journal": journal, "year": year},
    }

    return {"content": [{"type": "text", "text": json.dumps(doc, ensure_ascii=False)}]}


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )

