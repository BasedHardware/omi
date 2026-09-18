import html
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from models import ChatToolResponse

app = FastAPI(
    title="Omi PubMed App",
    description="PubMed chat tools for Omi",
    version="1.0.2",
)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = 20.0


def _safe(value: Any) -> str:
    """安全转换为字符串并解码 HTML 实体。"""
    return html.unescape(str(value)) if value is not None else ""


def _clean_pmid(value: Any) -> str:
    """从字符串、整数或 URL 中清洗并提取纯数字的 PubMed ID。

    支持场景：
    - 纯数字字符串或正整数：'31234567', 31234567
    - 带有前缀：'PMID: 31234567', 'pmid:31234567', '#31234567'
    - PubMed 完整链接：'https://pubmed.ncbi.nlm.nih.gov/31234567/'
    - NCBI 传统链接：'https://www.ncbi.nlm.nih.gov/pubmed/31234567'
    - Markdown 链接与多余括号引号
    """
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value).strip() if value > 0 else ""
    if not isinstance(value, str):
        return ""

    raw = value.strip()
    if not raw:
        return ""

    # 1. 优先匹配 PubMed 网页链接中的数字 ID
    url_match = re.search(
        r"(?:pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/(\d+)",
        raw,
        re.IGNORECASE,
    )
    if url_match:
        return url_match.group(1)

    # 2. 匹配 Markdown 格式链接中的数字 ID，优先提取带有明确 pmid 标识的数字
    md_pmid_match = re.search(
        r"\[[^\]]*?pmid[:\s#]*(\d{1,12})[^\]]*\]\([^)]+\)",
        raw,
        re.IGNORECASE,
    )
    if md_pmid_match and md_pmid_match.group(1).isdigit():
        return md_pmid_match.group(1)

    # 匹配纯数字标题的 Markdown 链接，例如 [31234567](https://...)
    md_num_match = re.search(r"\[\s*(\d{1,12})\s*\]\([^)]+\)", raw)
    if md_num_match and md_num_match.group(1).isdigit():
        return md_num_match.group(1)


    # 3. 剥离外层多余的引号、尖括号、圆括号、方括号等标点
    cleaned = raw.strip("\"'<>`()[]{}.,;: ")

    # 4. 剥离常见的前缀如 PMID:、pmid、#、id: 等
    cleaned = re.sub(
        r"^(?:pmid[:\s#]*|id[:\s#]*|#+)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip("\"'<>`()[]{}.,;: ")

    if cleaned == "0":
        return ""

    return cleaned



def _is_valid_pmid(pmid: str) -> bool:
    """验证 PMID 是否为 1 到 12 位的纯 ASCII 正整数。"""
    return (
        bool(pmid)
        and pmid.isascii()
        and pmid.isdigit()
        and 1 <= len(pmid) <= 12
        and int(pmid) > 0
    )


def _clamp_max_results(value: Any, default: int = 5) -> int:
    """将 max_results 限制在 1 到 10 之间，防御布尔值与极端溢出异常。"""
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(1, min(parsed, 10))


def _extract_abstract_from_efetch_xml(xml_text: str) -> str:
    """解析 efetch XML 并提取第一篇文章的摘要内容。"""
    if not xml_text or not isinstance(xml_text, str):
        return ""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    abstract_parts = root.findall(".//AbstractText")
    if not abstract_parts:
        return ""
    chunks = []
    for part in abstract_parts:
        label = (part.get("Label") or "").strip()
        text = "".join(part.itertext()).strip()
        if not text:
            continue
        chunks.append(f"{label}: {text}" if label else text)
    return " ".join(chunks).strip()


async def _fetch_abstract(client: httpx.AsyncClient, pmid: str) -> str:
    """ESummary 不包含摘要，通过 efetch XML 接口获取。"""
    resp = await client.get(
        f"{EUTILS}/efetch.fcgi",
        params={"db": "pubmed", "id": pmid, "retmode": "xml"},
    )
    resp.raise_for_status()
    return _extract_abstract_from_efetch_xml(resp.text)


def _extract_article_fields(record: Any) -> dict:
    """从 ESummary 记录中提取标准化字段，具备全面的类型防御。"""
    if not isinstance(record, dict):
        return {
            "title": "Untitled",
            "pubdate": "",
            "source": "",
            "doi": "",
            "authors": [],
            "abstract": "",
        }

    title = _safe(record.get("title") or "Untitled")
    pubdate = _safe(record.get("pubdate", ""))
    source = _safe(record.get("source", ""))
    doi = _safe(record.get("elocationid", ""))

    authors = []
    raw_authors = record.get("authors")
    if isinstance(raw_authors, list):
        for author in raw_authors[:8]:
            if isinstance(author, dict):
                name = _safe(author.get("name"))
                if name:
                    authors.append(name)
            elif isinstance(author, str) and author.strip():
                authors.append(_safe(author.strip()))

    abstract = ""
    raw_abstract = record.get("abstract")
    if isinstance(raw_abstract, list):
        abstract = " ".join(_safe(x) for x in raw_abstract if x)
    elif raw_abstract:
        abstract = _safe(raw_abstract)

    return {
        "title": title,
        "pubdate": pubdate,
        "source": source,
        "doi": doi,
        "authors": authors,
        "abstract": abstract,
    }


async def _fetch_json(client: httpx.AsyncClient, endpoint: str, params: dict) -> dict:
    """发送 GET 请求并解析 JSON。"""
    resp = await client.get(f"{EUTILS}/{endpoint}", params=params)
    resp.raise_for_status()
    return resp.json()


async def _search_ids(client: httpx.AsyncClient, query: str, retmax: int = 5) -> list[str]:
    """通过 esearch 查询匹配的 PubMed ID 列表。"""
    data = await _fetch_json(
        client,
        "esearch.fcgi",
        {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": _clamp_max_results(retmax),
            "sort": "relevance",
        },
    )
    return data.get("esearchresult", {}).get("idlist", [])


def _select_related_pmids(links: Any, source_pmid: Any, max_results: int) -> list[str]:
    """从相关链接中去重、过滤无效项、排除源 PMID 并截取指定数量。"""
    if not isinstance(links, list):
        return []
    cleaned_source = str(source_pmid).strip()
    seen = set()
    result = []
    for x in links:
        if x is None:
            continue
        val = str(x).strip()
        if (
            val
            and val != cleaned_source
            and val.isascii()
            and val.isdigit()
            and val not in seen
        ):
            seen.add(val)
            result.append(val)
            if len(result) >= max_results:
                break
    return result


async def _fetch_summaries(client: httpx.AsyncClient, ids: list[str]) -> dict:
    """批量获取文献概要数据。"""
    if not ids:
        return {}
    data = await _fetch_json(
        client,
        "esummary.fcgi",
        {"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
    )
    return data.get("result", {})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def home():
    return HTMLResponse(
        """
        <html><body style='font-family:sans-serif;max-width:680px;margin:40px auto;'>
        <h1>Omi PubMed App</h1>
        <p>Use PubMed search and article lookup from Omi chat.</p>
        <p>Manifest: <code>/.well-known/omi-tools.json</code></p>
        </body></html>
        """
    )


@app.get("/.well-known/omi-tools.json")
async def manifest():
    return {
        "tools": [
            {
                "name": "search_pubmed",
                "description": "Search PubMed by keywords and return relevant papers.",
                "endpoint": "/tools/search_pubmed",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "description": "1-10, default 5"},
                    },
                    "required": ["query"],
                },
                "auth_required": False,
                "status_message": "Searching PubMed...",
            },
            {
                "name": "get_pubmed_article",
                "description": "Get detailed citation and abstract for a PubMed ID.",
                "endpoint": "/tools/get_pubmed_article",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "pmid": {"type": "string", "description": "PubMed ID (numeric)"},
                    },
                    "required": ["pmid"],
                },
                "auth_required": False,
                "status_message": "Fetching PubMed article...",
            },
            {
                "name": "get_related_pubmed",
                "description": "Find related PubMed articles from a PubMed ID.",
                "endpoint": "/tools/get_related_pubmed",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "pmid": {"type": "string", "description": "PubMed ID (numeric)"},
                        "max_results": {"type": "integer", "description": "1-10, default 5"},
                    },
                    "required": ["pmid"],
                },
                "auth_required": False,
                "status_message": "Finding related PubMed articles...",
            },
        ]
    }


@app.get("/manifest.json")
async def manifest_alias():
    return await manifest()


@app.post("/tools/search_pubmed", response_model=ChatToolResponse, tags=["chat_tools"])
async def search_pubmed(request: Request):
    """关键词搜索 PubMed 论文。"""
    try:
        try:
            body = await request.json()
        except Exception:
            return ChatToolResponse(error="Malformed JSON request body")
        if not isinstance(body, dict):
            return ChatToolResponse(error="Request body must be a JSON object")

        raw_query = body.get("query")
        if isinstance(raw_query, bool) or raw_query is None:
            query = ""
        else:
            query = str(raw_query).strip()

        max_results = _clamp_max_results(body.get("max_results", 5))
        if not query:
            return ChatToolResponse(error="query is required")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            ids = await _search_ids(client, query, max_results)
            if not ids:
                return ChatToolResponse(result=f"No PubMed results found for: {query}")
            summaries = await _fetch_summaries(client, ids)

        lines = [f"Top PubMed results for: {query}"]
        for idx, result_pmid in enumerate(ids, start=1):
            row = summaries.get(result_pmid)
            if not isinstance(row, dict):
                row = {}
            title = _safe(row.get("title") or "Untitled")
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            meta_parts = [p for p in (journal, date) if p]
            meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""
            lines.append(f"{idx}. PMID {result_pmid}: {title}{meta_str}")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else "unknown"
        return ChatToolResponse(error=f"PubMed API error: HTTP {status_code}")
    except httpx.RequestError as e:
        return ChatToolResponse(error=f"PubMed network error: {e}")
    except Exception as e:
        return ChatToolResponse(error=f"PubMed search failed: {e}")


@app.post("/tools/get_pubmed_article", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_pubmed_article(request: Request):
    """根据 PubMed ID 获取单篇论文详情及摘要。"""
    try:
        try:
            body = await request.json()
        except Exception:
            return ChatToolResponse(error="Malformed JSON request body")
        if not isinstance(body, dict):
            return ChatToolResponse(error="Request body must be a JSON object")

        pmid = _clean_pmid(body.get("pmid"))
        if not pmid:
            return ChatToolResponse(error="pmid is required")
        if not _is_valid_pmid(pmid):
            return ChatToolResponse(error="pmid must be a numeric PubMed ID")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            summaries = await _fetch_summaries(client, [pmid])
            record = summaries.get(pmid)
            if (
                not isinstance(record, dict)
                or "error" in record
                or not record.get("title")
            ):
                return ChatToolResponse(error=f"No PubMed record found for PMID {pmid}")

            # 尝试通过 efetch 获取完整的正文摘要
            try:
                abstract = await _fetch_abstract(client, pmid)
            except Exception:
                abstract = ""
            if abstract and isinstance(summaries.get(pmid), dict):
                summaries[pmid]["abstract"] = abstract

        record = _extract_article_fields(summaries[pmid])
        lines = [
            f"PMID {pmid}",
            f"Title: {record['title']}",
            f"Authors: {', '.join(record['authors']) if record['authors'] else 'N/A'}",
            f"Journal/Date: {record['source']} ({record['pubdate']})",
            f"DOI/Location: {record['doi'] or 'N/A'}",
        ]
        if record["abstract"]:
            lines.append(f"Abstract: {record['abstract'][:1800]}")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else "unknown"
        return ChatToolResponse(error=f"PubMed API error: HTTP {status_code}")
    except httpx.RequestError as e:
        return ChatToolResponse(error=f"PubMed network error: {e}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch PubMed article: {e}")


@app.post("/tools/get_related_pubmed", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_related_pubmed(request: Request):
    """根据 PubMed ID 获取相关联的论文列表。"""
    try:
        try:
            body = await request.json()
        except Exception:
            return ChatToolResponse(error="Malformed JSON request body")
        if not isinstance(body, dict):
            return ChatToolResponse(error="Request body must be a JSON object")

        pmid = _clean_pmid(body.get("pmid"))
        max_results = _clamp_max_results(body.get("max_results", 5))
        if not pmid:
            return ChatToolResponse(error="pmid is required")
        if not _is_valid_pmid(pmid):
            return ChatToolResponse(error="pmid must be a numeric PubMed ID")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            data = await _fetch_json(
                client,
                "elink.fcgi",
                {
                    "dbfrom": "pubmed",
                    "db": "pubmed",
                    "id": pmid,
                    "linkname": "pubmed_pubmed",
                    "retmode": "json",
                },
            )

            linksets = data.get("linksets", [])
            related = []
            if linksets and isinstance(linksets, list):
                dbs = linksets[0].get("linksetdbs", []) if isinstance(linksets[0], dict) else []
                if dbs and isinstance(dbs, list) and isinstance(dbs[0], dict):
                    related = _select_related_pmids(dbs[0].get("links", []), pmid, max_results)

            if not related:
                return ChatToolResponse(result=f"No related articles found for PMID {pmid}")

            summaries = await _fetch_summaries(client, related)

        lines = [f"Related PubMed articles for PMID {pmid}:"]
        for idx, related_pmid in enumerate(related, start=1):
            row = summaries.get(related_pmid)
            if not isinstance(row, dict):
                row = {}
            title = _safe(row.get("title") or "Untitled")
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            meta_parts = [p for p in (journal, date) if p]
            meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""
            lines.append(f"{idx}. PMID {related_pmid}: {title}{meta_str}")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response is not None else "unknown"
        return ChatToolResponse(error=f"PubMed API error: HTTP {status_code}")
    except httpx.RequestError as e:
        return ChatToolResponse(error=f"PubMed network error: {e}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch related PubMed articles: {e}")
