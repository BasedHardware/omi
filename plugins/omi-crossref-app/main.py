from contextlib import asynccontextmanager
import html
import re
from typing import Any
from urllib.parse import quote, unquote

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput

CROSSREF_BASE = "https://api.crossref.org"
TIMEOUT = 20.0
USER_AGENT = "OmiCrossrefPlugin/1.0 (https://github.com/BasedHardware/omi; mailto:dev@omi.me)"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理持久化的 HTTP 客户端连接池，避免连接耗尽与套接字流失。"""
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        app.state.client = client
        yield
    app.state.client = None


app = FastAPI(
    title="Crossref Omi Integration",
    description="No-auth Crossref chat tools for paper metadata search and lookup",
    version="1.0.1",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """统一拦截请求验证错误，遵守 Omi HTTP 200 ChatToolResponse 错误返回契约。"""
    first_err = exc.errors()[0] if exc.errors() else {}
    detail = first_err.get("msg", "invalid request payload")
    return JSONResponse(
        status_code=200,
        content=ChatToolResponse(error=f"Invalid request: {detail}").model_dump(),
    )


def clamp_max_results(value: Any, default: int = 5) -> int:
    """将 max_results 限制在 1 到 10 之间，排除布尔值与溢出异常。"""
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(1, min(10, parsed))


def clean_doi(value: Any) -> str:
    """从字符串、URL 或 Markdown 链接中清洗并提取标准化的 DOI。

    支持场景：
    - 纯 DOI：'10.1038/nphys1170'，包含加号、括号等合法符号：'10.1021/jp035848+'
    - 带前缀：'doi: 10.1038/nphys1170', 'DOI:10.1038/nphys1170'
    - 网页链接：'https://doi.org/10.1038/nphys1170', 'http://dx.doi.org/10.1038/nphys1170'
    - API 链接：'https://api.crossref.org/works/10.1038/nphys1170'
    - Markdown 链接：'[DOI](https://doi.org/10.1038/nphys1170)'
    - 去除外层引号、尖括号、未配对标点
    """
    if value is None or isinstance(value, bool) or not isinstance(value, str):
        return ""

    raw = value.strip()
    if not raw:
        return ""

    # 1. 优先执行 URL 解码，防止整段百分号编码导致协议头匹配失败
    try:
        raw = unquote(raw).strip()
    except Exception:
        pass

    # 2. 匹配标准 DOI 格式（10.xxxx/...），支持加号、尖括号与常见学术特殊符号
    doi_pattern = re.search(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9+<>]+)", raw)
    if doi_pattern:
        candidate = doi_pattern.group(1).rstrip(".,;:\"'")
        # 若以右括号结尾且整体不配对，剔除多余右括号
        if candidate.endswith(")") and candidate.count(")") > candidate.count("("):
            candidate = candidate.rstrip(")")
        # 若以右尖括号结尾且整体不配对，剔除多余右尖括号
        if candidate.endswith(">") and candidate.count(">") > candidate.count("<"):
            candidate = candidate.rstrip(">")
        return candidate

    # 3. 剥离 Markdown 链接语法
    md_match = re.search(r"\[[^\]]*\]\(([^)]+)\)", raw)
    if md_match:
        target = md_match.group(1).strip()
        doi_in_url = re.search(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9+<>]+)", target)
        if doi_in_url:
            candidate = doi_in_url.group(1).rstrip(".,;:\"'")
            if candidate.endswith(")") and candidate.count(")") > candidate.count("("):
                candidate = candidate.rstrip(")")
            if candidate.endswith(">") and candidate.count(">") > candidate.count("<"):
                candidate = candidate.rstrip(">")
            return candidate


    # 4. 剥离常见 URL 前缀与协议头
    cleaned = raw.strip("\"'<>`()[]{}.,;: ")
    cleaned = re.sub(
        r"^(?:https?://)?(?:dx\.)?doi\.org/",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^https?://api\.crossref\.org/works/",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^doi:\s*", "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned.strip("\"'<>`[]{}.,;: ")


_JATS_TAG = re.compile(r"</?jats:[^>]+>")
# 闭合标签绝不是不等号，直接剥离
_CLOSE_TAG = re.compile(r"</[a-zA-Z][^>]*>")
# 开启标签必须紧随完整合法标签名，避免误删学术不等式如 p < 0.05
_OPEN_TAG = re.compile(r"(?<![A-Za-z0-9_])<[a-zA-Z][a-zA-Z0-9:-]*(?:\s+[^>]*)?>")


def clean(text: Any) -> str:
    """清理字符串、剥离 JATS/HTML 标签并解码 HTML 实体。"""
    if text is None:
        return ""
    if isinstance(text, (list, tuple)):
        return clean(text[0]) if text else ""
    value = html.unescape(str(text)).strip()
    # Crossref 摘要常包含 JATS 标签，转换为纯文本
    value = _JATS_TAG.sub("", value)
    value = _CLOSE_TAG.sub("", value)
    value = _OPEN_TAG.sub("", value)
    return value.strip()


def _extract_title(item: dict[str, Any]) -> str:
    """从作品字典中提取文章标题，兼顾列表与字符串形态。"""
    if not isinstance(item, dict):
        return "Untitled"
    raw_title = item.get("title")
    if isinstance(raw_title, list):
        for t in raw_title:
            cleaned = clean(t)
            if cleaned:
                return cleaned
        return "Untitled"
    if isinstance(raw_title, str) and raw_title.strip():
        return clean(raw_title)
    return "Untitled"


def extract_year(item: dict[str, Any]) -> str:
    """从作品字典中安全提取发表年份，防御嵌套缺失或非字典结构。"""
    if not isinstance(item, dict):
        return ""
    for key in ("published-print", "published-online", "issued"):
        date_obj = item.get(key)
        if not isinstance(date_obj, dict):
            continue
        date_parts = date_obj.get("date-parts")
        if (
            isinstance(date_parts, list)
            and date_parts
            and isinstance(date_parts[0], list)
            and date_parts[0]
        ):
            year_val = date_parts[0][0]
            if year_val is not None:
                return clean(year_val)
    return ""


async def crossref_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """发送 GET 请求到 Crossref API，优先使用 lifespan 连接池，遇关闭或未初始化时优雅回退。"""
    headers = {"User-Agent": USER_AGENT}
    client = getattr(getattr(app, "state", None), "client", None)
    if client is not None and not getattr(client, "is_closed", False):
        response = await client.get(f"{CROSSREF_BASE}{path}", params=params)
        response.raise_for_status()
        return response.json()

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as fallback_client:
        response = await fallback_client.get(f"{CROSSREF_BASE}{path}", params=params)
        response.raise_for_status()
        return response.json()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def tools():
    return {
        "tools": [
            {
                "name": "search_crossref_works",
                "description": "Search scholarly works by keyword via Crossref",
                "parameters": {
                    "query": {"type": "string", "description": "Search keyword(s)"},
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1-10)",
                        "default": 5,
                    },
                },
            },
            {
                "name": "get_crossref_work",
                "description": "Get details for a specific work by DOI",
                "parameters": {
                    "doi": {
                        "type": "string",
                        "description": "DOI, e.g. 10.1038/nphys1170",
                    }
                },
            },
            {
                "name": "get_crossref_works_by_author",
                "description": "Find recent works for an author name",
                "parameters": {
                    "author": {"type": "string", "description": "Author name"},
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1-10)",
                        "default": 5,
                    },
                },
            },
        ]
    }


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    return {
        "tools": [
            {
                "name": "search_crossref_works",
                "description": "Search scholarly works by keyword via Crossref",
                "endpoint": "/tools/search_crossref_works",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword(s)"},
                        "max_results": {
                            "type": "integer",
                            "description": "Number of results (1-10)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
                "auth_required": False,
                "status_message": "Searching Crossref...",
            },
            {
                "name": "get_crossref_work",
                "description": "Get details for a specific work by DOI",
                "endpoint": "/tools/get_crossref_work",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "doi": {
                            "type": "string",
                            "description": "DOI, e.g. 10.1038/nphys1170",
                        }
                    },
                    "required": ["doi"],
                },
                "auth_required": False,
                "status_message": "Fetching Crossref work...",
            },
            {
                "name": "get_crossref_works_by_author",
                "description": "Find recent works for an author name",
                "endpoint": "/tools/get_crossref_works_by_author",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "author": {"type": "string", "description": "Author name"},
                        "max_results": {
                            "type": "integer",
                            "description": "Number of results (1-10)",
                            "default": 5,
                        },
                    },
                    "required": ["author"],
                },
                "auth_required": False,
                "status_message": "Fetching author works...",
            },
        ]
    }


@app.post("/tools/search_crossref_works", response_model=ChatToolResponse)
async def search_crossref_works(payload: SearchWorksInput):
    """关键词搜索 Crossref 学术文献。"""
    query = str(payload.query or "").strip()
    if len(query) < 2:
        return ChatToolResponse(error="Query must be at least 2 characters.")
    limited = clamp_max_results(payload.max_results)
    try:
        data = await crossref_get(
            "/works",
            {"query": query, "rows": limited, "sort": "relevance", "order": "desc"},
        )
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        return ChatToolResponse(error=f"Crossref API error: HTTP {code}")
    except httpx.RequestError as exc:
        return ChatToolResponse(error=f"Crossref network error: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    message = data.get("message") if isinstance(data, dict) else {}
    raw_items = message.get("items") if isinstance(message, dict) else []
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []

    if not items:
        return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

    lines = [f"Top {len(items)} Crossref results for '{query}':"]
    for idx, item in enumerate(items, 1):
        title = _extract_title(item)
        doi = clean(item.get("DOI"))
        year = extract_year(item)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_crossref_work", response_model=ChatToolResponse)
async def get_crossref_work(payload: GetWorkInput):
    """根据 DOI 获取单篇论文的详细元数据。"""
    normalized = clean_doi(payload.doi)
    if not normalized or not normalized.startswith("10.") or "/" not in normalized:
        return ChatToolResponse(error="Invalid DOI format. Example: 10.1038/nphys1170")
    if ".." in normalized:
        return ChatToolResponse(error="Invalid DOI value.")

    try:
        data = await crossref_get(f"/works/{quote(normalized, safe='')}", {})
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        if code == 404:
            return ChatToolResponse(error=f"Work not found for DOI: {normalized}")
        return ChatToolResponse(error=f"Crossref API error: HTTP {code}")
    except httpx.RequestError as exc:
        return ChatToolResponse(error=f"Crossref network error: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    item = data.get("message", {}) if isinstance(data, dict) else {}
    if not isinstance(item, dict) or not item:
        return ChatToolResponse(error=f"Work not found for DOI: {normalized}")

    title = _extract_title(item)
    publisher = clean(item.get("publisher"))
    doi_out = clean(item.get("DOI")) or normalized
    url = clean(item.get("URL"))
    abstract = clean(item.get("abstract"))
    year = extract_year(item)

    parts = [
        f"Title: {title}",
        f"DOI: {doi_out}",
        f"Year: {year}",
        f"Publisher: {publisher}",
        f"URL: {url}",
    ]
    if abstract:
        parts.append(f"Abstract: {abstract[:1200]}")
    return ChatToolResponse(result="\n".join(parts))


@app.post("/tools/get_crossref_works_by_author", response_model=ChatToolResponse)
async def get_crossref_works_by_author(payload: AuthorWorksInput):
    """根据作者姓名查找近期文献。"""
    author = str(payload.author or "").strip()
    if len(author) < 2:
        return ChatToolResponse(error="Author must be at least 2 characters.")
    limited = clamp_max_results(payload.max_results)
    try:
        data = await crossref_get(
            "/works",
            {
                "query.author": author,
                "rows": limited,
                "sort": "published",
                "order": "desc",
            },
        )
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        return ChatToolResponse(error=f"Crossref API error: HTTP {code}")
    except httpx.RequestError as exc:
        return ChatToolResponse(error=f"Crossref network error: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    message = data.get("message") if isinstance(data, dict) else {}
    raw_items = message.get("items") if isinstance(message, dict) else []
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []

    if not items:
        return ChatToolResponse(result=f"No recent works found for author '{author}'.")

    lines = [f"Recent works for '{author}':"]
    for idx, item in enumerate(items, 1):
        title = _extract_title(item)
        doi = clean(item.get("DOI"))
        year = extract_year(item)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))
