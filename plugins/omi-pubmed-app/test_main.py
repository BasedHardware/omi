"""Omi PubMed 插件的全量密封单元测试（Hermetic Unit Tests）。

无需第三方运行时依赖（0 外部网络连接，完全在内存中运行）。
能够在无外部依赖的纯标准库（python3 -S）以及 pytest 环境下确定性运行。
覆盖清洗提取、边界防御、XML 解析、文章字段标准化与所有 chat-tool 接口。
"""

import asyncio
import html
import os
import re
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = ("httpx", "fastapi", "fastapi.responses", "pydantic")


def _install_module_stubs():
    # 模拟 httpx
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class RequestError(HTTPError):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, request=None, response=None):
            super().__init__(message)
            self.request = request
            self.response = response

    class ConnectError(RequestError):
        pass

    class TimeoutException(RequestError):
        pass

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *args, **kwargs):
            raise AssertionError("测试中严禁进行真实网络请求，必须 mock 处理")

    httpx.HTTPError = HTTPError
    httpx.RequestError = RequestError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.ConnectError = ConnectError
    httpx.TimeoutException = TimeoutException
    httpx.AsyncClient = _AsyncClient
    sys.modules["httpx"] = httpx

    # 模拟 fastapi
    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            self.routes = []

        def get(self, path, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def post(self, path, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    class Request:
        def __init__(self, json_data=None):
            self._json_data = json_data

        async def json(self):
            if isinstance(self._json_data, Exception):
                raise self._json_data
            return self._json_data

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    sys.modules["fastapi"] = fastapi

    # 模拟 fastapi.responses
    fastapi_responses = types.ModuleType("fastapi.responses")

    class HTMLResponse:
        def __init__(self, content="", status_code=200):
            self.content = content
            self.status_code = status_code

    fastapi_responses.HTMLResponse = HTMLResponse
    sys.modules["fastapi.responses"] = fastapi_responses

    # 模拟 pydantic
    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic


# 保存并安装 stubs
_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    import main
    from models import ChatToolResponse
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original


def _run(coro):
    return asyncio.run(coro)


class CleanPmidTests(unittest.TestCase):
    """测试 _clean_pmid 的各种输入清洗与提取能力。"""

    def test_numeric_string_and_int(self):
        self.assertEqual(main._clean_pmid("31234567"), "31234567")
        self.assertEqual(main._clean_pmid(31234567), "31234567")
        self.assertEqual(main._clean_pmid("  31234567  "), "31234567")

    def test_prefixes(self):
        self.assertEqual(main._clean_pmid("PMID: 31234567"), "31234567")
        self.assertEqual(main._clean_pmid("pmid:31234567"), "31234567")
        self.assertEqual(main._clean_pmid("pmid 31234567"), "31234567")
        self.assertEqual(main._clean_pmid("#31234567"), "31234567")
        self.assertEqual(main._clean_pmid("id: 31234567"), "31234567")

    def test_pubmed_urls(self):
        self.assertEqual(
            main._clean_pmid("https://pubmed.ncbi.nlm.nih.gov/31234567/"),
            "31234567",
        )
        self.assertEqual(
            main._clean_pmid("http://pubmed.ncbi.nlm.nih.gov/31234567"),
            "31234567",
        )
        self.assertEqual(
            main._clean_pmid("https://www.ncbi.nlm.nih.gov/pubmed/31234567?dopt=Abstract"),
            "31234567",
        )

    def test_markdown_links_and_quotes(self):
        self.assertEqual(
            main._clean_pmid("[PubMed 31234567](https://pubmed.ncbi.nlm.nih.gov/31234567/)"),
            "31234567",
        )
        self.assertEqual(main._clean_pmid('"31234567"'), "31234567")
        self.assertEqual(main._clean_pmid("`31234567`"), "31234567")
        # 验证 Markdown 标题中含有年份时不会误匹配年份
        self.assertEqual(
            main._clean_pmid("[2024 Study on Cancer (PMID 31234567)](https://doi.org/10.1038)"),
            "31234567",
        )
        # 验证括号标点剥离
        self.assertEqual(main._clean_pmid("(PMID: 31234567)"), "31234567")
        self.assertEqual(main._clean_pmid("31234567."), "31234567")

    def test_invalid_and_empty_inputs(self):
        self.assertEqual(main._clean_pmid(None), "")
        self.assertEqual(main._clean_pmid(""), "")
        self.assertEqual(main._clean_pmid("   "), "")
        self.assertEqual(main._clean_pmid(True), "")
        self.assertEqual(main._clean_pmid(False), "")
        self.assertEqual(main._clean_pmid(0), "")
        self.assertEqual(main._clean_pmid("0"), "")
        self.assertEqual(main._clean_pmid(-10), "")
        self.assertEqual(main._clean_pmid("cancer_review"), "cancer_review")


class IsValidPmidTests(unittest.TestCase):
    """测试 _is_valid_pmid 对 ASCII 纯数字及零值的严格校验。"""

    def test_valid_pmids(self):
        self.assertTrue(main._is_valid_pmid("12345"))
        self.assertTrue(main._is_valid_pmid("31234567"))

    def test_invalid_pmids(self):
        self.assertFalse(main._is_valid_pmid("0"))
        self.assertFalse(main._is_valid_pmid("0000"))
        self.assertFalse(main._is_valid_pmid(""))
        self.assertFalse(main._is_valid_pmid("abc"))
        self.assertFalse(main._is_valid_pmid("１２３"))  # 全角数字必须被拦截
        self.assertFalse(main._is_valid_pmid("1234567890123"))  # 超过 12 位


class ClampMaxResultsTests(unittest.TestCase):
    """测试 _clamp_max_results 的数值约束与类型防御。"""

    def test_valid_ranges(self):
        self.assertEqual(main._clamp_max_results(1), 1)
        self.assertEqual(main._clamp_max_results(5), 5)
        self.assertEqual(main._clamp_max_results(10), 10)

    def test_clamping_bounds(self):
        self.assertEqual(main._clamp_max_results(0), 1)
        self.assertEqual(main._clamp_max_results(-5), 1)
        self.assertEqual(main._clamp_max_results(20), 10)

    def test_string_and_invalid_types(self):
        self.assertEqual(main._clamp_max_results("7"), 7)
        self.assertEqual(main._clamp_max_results("bad"), 5)
        self.assertEqual(main._clamp_max_results(None), 5)
        self.assertEqual(main._clamp_max_results(True), 5)
        self.assertEqual(main._clamp_max_results(False), 5)
        # 极端大数与浮点无穷大防御（OverflowError）
        self.assertEqual(main._clamp_max_results(float("inf")), 5)

        self.assertEqual(main._clamp_max_results("bad"), 5)
        self.assertEqual(main._clamp_max_results(None), 5)
        self.assertEqual(main._clamp_max_results(True), 5)
        self.assertEqual(main._clamp_max_results(False), 5)


class ExtractArticleFieldsTests(unittest.TestCase):
    """测试 _extract_article_fields 的防御性数据解析。"""

    def test_normal_record(self):
        rec = {
            "title": "Study of Genetics",
            "pubdate": "2024 Jan 1",
            "source": "Nature",
            "elocationid": "10.1038/xyz",
            "authors": [{"name": "Alice"}, {"name": "Bob"}],
            "abstract": "Key genetic findings.",
        }
        res = main._extract_article_fields(rec)
        self.assertEqual(res["title"], "Study of Genetics")
        self.assertEqual(res["pubdate"], "2024 Jan 1")
        self.assertEqual(res["source"], "Nature")
        self.assertEqual(res["doi"], "10.1038/xyz")
        self.assertEqual(res["authors"], ["Alice", "Bob"])
        self.assertEqual(res["abstract"], "Key genetic findings.")

    def test_non_dict_record(self):
        res = main._extract_article_fields(None)
        self.assertEqual(res["title"], "Untitled")
        self.assertEqual(res["authors"], [])

    def test_author_variations(self):
        rec = {
            "title": "Test",
            "authors": ["Alice", None, {"name": "Bob"}, {"invalid": 123}],
        }
        res = main._extract_article_fields(rec)
        self.assertEqual(res["authors"], ["Alice", "Bob"])

    def test_abstract_variations(self):
        rec_list = {"abstract": ["Background:", "Results:"]}
        self.assertEqual(main._extract_article_fields(rec_list)["abstract"], "Background: Results:")

    def test_html_unescaping(self):
        rec = {"title": "&lt;b&gt;CRISPR&lt;/b&gt; &amp; Cas9"}
        self.assertEqual(main._extract_article_fields(rec)["title"], "<b>CRISPR</b> & Cas9")


class ExtractAbstractXmlTests(unittest.TestCase):
    """测试 XML 摘要解析。"""

    def test_labeled_sections(self):
        xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation><Article><Abstract>
            <AbstractText Label="AIM">Identify virus.</AbstractText>
            <AbstractText Label="METHOD">PCR.</AbstractText>
        </Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
        abstract = main._extract_abstract_from_efetch_xml(xml)
        self.assertIn("AIM: Identify virus.", abstract)
        self.assertIn("METHOD: PCR.", abstract)

    def test_empty_or_invalid_xml(self):
        self.assertEqual(main._extract_abstract_from_efetch_xml(""), "")
        self.assertEqual(main._extract_abstract_from_efetch_xml("<invalid xml"), "")
        self.assertEqual(main._extract_abstract_from_efetch_xml("<PubmedArticleSet></PubmedArticleSet>"), "")


class SelectRelatedPmidsTests(unittest.TestCase):
    """测试 _select_related_pmids 排除源 PMID 并限流。"""

    def test_filtering(self):
        links = ["100", "200", "300"]
        self.assertEqual(main._select_related_pmids(links, "100", 5), ["200", "300"])
        self.assertEqual(main._select_related_pmids(links, 200, 1), ["100"])

    def test_non_list_or_none(self):
        self.assertEqual(main._select_related_pmids(None, "100", 5), [])
        self.assertEqual(main._select_related_pmids("not a list", "100", 5), [])


class EndpointTests(unittest.TestCase):
    """测试所有 FastAPI endpoints 的业务逻辑、错误捕获与状态返回。"""

    def _dummy_request(self, payload):
        req = types.SimpleNamespace()
        async def json():
            if isinstance(payload, Exception):
                raise payload
            return payload
        req.json = json
        return req

    def test_health(self):
        res = _run(main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_manifest(self):
        res = _run(main.manifest())
        self.assertIn("tools", res)
        tool_names = [t["name"] for t in res["tools"]]
        self.assertIn("search_pubmed", tool_names)
        self.assertIn("get_pubmed_article", tool_names)
        self.assertIn("get_related_pubmed", tool_names)

    def test_search_pubmed_success(self):
        mock_esearch = {"esearchresult": {"idlist": ["123", "456"]}}
        mock_esummary = {
            "result": {
                "123": {"title": "Paper 1", "source": "Lancet", "pubdate": "2023"},
                "456": {"title": "Paper 2", "fulljournalname": "NEJM", "pubdate": "2024"},
            }
        }
        with mock.patch.object(main, "_fetch_json", side_effect=[mock_esearch, mock_esummary]):
            res = _run(main.search_pubmed(self._dummy_request({"query": "cancer", "max_results": 2})))
            self.assertIsNone(res.error)
            self.assertIn("Top PubMed results for: cancer", res.result)
            self.assertIn("Paper 1", res.result)
            self.assertIn("Paper 2", res.result)

    def test_search_pubmed_empty_query(self):
        res = _run(main.search_pubmed(self._dummy_request({"query": "   "})))
        self.assertEqual(res.error, "query is required")

    def test_search_pubmed_invalid_body(self):
        res = _run(main.search_pubmed(self._dummy_request("not-a-dict")))
        self.assertEqual(res.error, "Request body must be a JSON object")

    def test_search_pubmed_no_results(self):
        mock_esearch = {"esearchresult": {"idlist": []}}
        with mock.patch.object(main, "_fetch_json", return_value=mock_esearch):
            res = _run(main.search_pubmed(self._dummy_request({"query": "unknown_term_xyz"})))
            self.assertIn("No PubMed results found for: unknown_term_xyz", res.result)

    def test_search_pubmed_http_error(self):
        mock_resp = types.SimpleNamespace(status_code=429)
        err = main.httpx.HTTPStatusError("Rate Limit", response=mock_resp)
        with mock.patch.object(main, "_fetch_json", side_effect=err):
            res = _run(main.search_pubmed(self._dummy_request({"query": "cancer"})))
            self.assertIn("PubMed API error: HTTP 429", res.error)

    def test_get_pubmed_article_success_with_url(self):
        mock_summary = {
            "result": {
                "31234567": {
                    "title": "Novel Therapy",
                    "pubdate": "2023",
                    "source": "Nature",
                    "elocationid": "10.1038/s41586",
                    "authors": [{"name": "John Doe"}],
                }
            }
        }
        with mock.patch.object(main, "_fetch_summaries", return_value=mock_summary["result"]), \
             mock.patch.object(main, "_fetch_abstract", return_value="Detailed therapeutic findings."):
            req = self._dummy_request({"pmid": "https://pubmed.ncbi.nlm.nih.gov/31234567/"})
            res = _run(main.get_pubmed_article(req))
            self.assertIsNone(res.error)
            self.assertIn("PMID 31234567", res.result)
            self.assertIn("Novel Therapy", res.result)
            self.assertIn("Detailed therapeutic findings.", res.result)

    def test_get_pubmed_article_integer_pmid(self):
        mock_summary = {
            "result": {
                "31234567": {
                    "title": "Integer PMID Paper",
                    "source": "Science",
                    "pubdate": "2024",
                }
            }
        }
        with mock.patch.object(main, "_fetch_summaries", return_value=mock_summary["result"]), \
             mock.patch.object(main, "_fetch_abstract", return_value=""):
            req = self._dummy_request({"pmid": 31234567})
            res = _run(main.get_pubmed_article(req))
            self.assertIsNone(res.error)
            self.assertIn("PMID 31234567", res.result)
            self.assertIn("Integer PMID Paper", res.result)

    def test_get_pubmed_article_invalid_pmid(self):
        res = _run(main.get_pubmed_article(self._dummy_request({"pmid": "abc_not_numeric"})))
        self.assertEqual(res.error, "pmid must be a numeric PubMed ID")

    def test_get_pubmed_article_missing_pmid(self):
        res = _run(main.get_pubmed_article(self._dummy_request({})))
        self.assertEqual(res.error, "pmid is required")

    def test_search_pubmed_malformed_json(self):
        req = types.SimpleNamespace()
        async def json():
            raise ValueError("Malformed JSON")
        req.json = json
        res = _run(main.search_pubmed(req))
        self.assertEqual(res.error, "Malformed JSON request body")

    def test_search_pubmed_with_none_summary_row(self):
        mock_esearch = {"esearchresult": {"idlist": ["123"]}}
        mock_esummary = {"result": {"123": None}}  # 上游返回空行，不能崩
        with mock.patch.object(main, "_fetch_json", side_effect=[mock_esearch, mock_esummary]):
            res = _run(main.search_pubmed(self._dummy_request({"query": "cancer"})))
            self.assertIsNone(res.error)
            self.assertIn("PMID 123: Untitled", res.result)

    def test_get_pubmed_article_not_found(self):
        with mock.patch.object(main, "_fetch_summaries", return_value={}):
            res = _run(main.get_pubmed_article(self._dummy_request({"pmid": "99999999"})))
            self.assertEqual(res.error, "No PubMed record found for PMID 99999999")

    def test_get_pubmed_article_not_found_with_upstream_error(self):
        # 模拟真实 NCBI ESummary 返回的错误字典，绝不能伪造成功返回
        mock_error_summary = {
            "uids": [],
            "99999999": {"error": "cannot get document summary"},
        }
        with mock.patch.object(main, "_fetch_summaries", return_value=mock_error_summary):
            res = _run(main.get_pubmed_article(self._dummy_request({"pmid": "99999999"})))
            self.assertEqual(res.error, "No PubMed record found for PMID 99999999")
            self.assertIsNone(res.result)


    def test_get_related_pubmed_success(self):
        mock_elink = {
            "linksets": [
                {
                    "linksetdbs": [
                        {"links": ["31234567", "11111", "22222"]}
                    ]
                }
            ]
        }
        mock_summaries = {
            "11111": {"title": "Related 1", "source": "Journal A", "pubdate": "2022"},
            "22222": {"title": "Related 2", "source": "Journal B", "pubdate": "2023"},
        }
        with mock.patch.object(main, "_fetch_json", return_value=mock_elink), \
             mock.patch.object(main, "_fetch_summaries", return_value=mock_summaries):
            req = self._dummy_request({"pmid": "PMID: 31234567", "max_results": 2})
            res = _run(main.get_related_pubmed(req))
            self.assertIsNone(res.error)
            self.assertIn("Related PubMed articles for PMID 31234567:", res.result)
            self.assertIn("PMID 11111: Related 1", res.result)
            self.assertIn("PMID 22222: Related 2", res.result)

    def test_get_related_pubmed_none_found(self):
        mock_elink = {"linksets": []}
        with mock.patch.object(main, "_fetch_json", return_value=mock_elink):
            res = _run(main.get_related_pubmed(self._dummy_request({"pmid": "31234567"})))
            self.assertIn("No related articles found for PMID 31234567", res.result)


if __name__ == "__main__":
    unittest.main()
