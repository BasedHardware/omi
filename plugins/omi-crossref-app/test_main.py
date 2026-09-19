"""Omi Crossref 插件全量密封单元测试（Hermetic Unit Tests）。

无需第三方运行时依赖（0 外部网络连接，完全在内存中运行）。
能够在无外部依赖的纯标准库（python3 -S）以及 pytest 环境下确定性运行。
覆盖 DOI 清洗提取、JATS 标签过滤、嵌套日期防御、标题健壮性与所有 chat-tool 接口。
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = (
    "httpx",
    "fastapi",
    "fastapi.exceptions",
    "fastapi.responses",
    "pydantic",
)


def _install_module_stubs():
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
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            self.is_closed = True
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

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, path, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def post(self, path, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def exception_handler(self, exc_class):
            def decorator(func):
                return func
            return decorator

    class Request:
        pass

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    sys.modules["fastapi"] = fastapi

    fastapi_exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationError(Exception):
        def __init__(self, errors=None):
            self._errors = errors or []

        def errors(self):
            return self._errors

    fastapi_exceptions.RequestValidationError = RequestValidationError
    sys.modules["fastapi.exceptions"] = fastapi_exceptions

    fastapi_responses = types.ModuleType("fastapi.responses")

    class JSONResponse:
        def __init__(self, status_code=200, content=None):
            self.status_code = status_code
            self.content = content

    fastapi_responses.JSONResponse = JSONResponse
    sys.modules["fastapi.responses"] = fastapi_responses

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
    from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original


def _run(coro):
    return asyncio.run(coro)


class CleanDoiTests(unittest.TestCase):
    """测试 clean_doi 对各种格式、URL、Markdown 链接的清洗与提取。"""

    def test_clean_doi_standard(self):
        self.assertEqual(main.clean_doi("10.1038/nphys1170"), "10.1038/nphys1170")
        self.assertEqual(main.clean_doi("  10.1038/nphys1170  "), "10.1038/nphys1170")

    def test_clean_doi_with_prefix(self):
        self.assertEqual(main.clean_doi("doi: 10.1038/nphys1170"), "10.1038/nphys1170")
        self.assertEqual(main.clean_doi("DOI:10.1038/nphys1170"), "10.1038/nphys1170")

    def test_clean_doi_urls(self):
        self.assertEqual(
            main.clean_doi("https://doi.org/10.1038/nphys1170"),
            "10.1038/nphys1170",
        )
        self.assertEqual(
            main.clean_doi("http://dx.doi.org/10.1038/nphys1170"),
            "10.1038/nphys1170",
        )
        self.assertEqual(
            main.clean_doi("https://api.crossref.org/works/10.1038/nphys1170"),
            "10.1038/nphys1170",
        )

    def test_clean_doi_markdown_links(self):
        self.assertEqual(
            main.clean_doi("[10.1038/nphys1170](https://doi.org/10.1038/nphys1170)"),
            "10.1038/nphys1170",
        )
        self.assertEqual(
            main.clean_doi("[Paper Link](https://doi.org/10.1038/nphys1170)"),
            "10.1038/nphys1170",
        )

    def test_clean_doi_special_chars_and_encoding(self):
        # 验证包含加号的化学/物理 DOI
        self.assertEqual(main.clean_doi("10.1021/jp035848+"), "10.1021/jp035848+")
        # 验证整段 URL 百分号编码的链接清洗
        self.assertEqual(
            main.clean_doi("https%3A%2F%2Fdoi.org%2F10.1038%2Fnphys1170"),
            "10.1038/nphys1170",
        )
        # 验证包含成对括号的合法 DOI
        self.assertEqual(
            main.clean_doi("10.1002/(SICI)1097-0142(19961115)78:10<2183::AID-CNCR20>3.0.CO;2-T"),
            "10.1002/(SICI)1097-0142(19961115)78:10<2183::AID-CNCR20>3.0.CO;2-T",
        )

    def test_clean_doi_punctuations_and_quotes(self):
        self.assertEqual(main.clean_doi('"10.1038/nphys1170"'), "10.1038/nphys1170")
        self.assertEqual(main.clean_doi("<10.1038/nphys1170>"), "10.1038/nphys1170")
        self.assertEqual(main.clean_doi("(10.1038/nphys1170)."), "10.1038/nphys1170")

    def test_clean_doi_invalid_inputs(self):
        self.assertEqual(main.clean_doi(None), "")
        self.assertEqual(main.clean_doi(""), "")
        self.assertEqual(main.clean_doi(True), "")
        self.assertEqual(main.clean_doi(False), "")
        self.assertEqual(main.clean_doi("not_a_doi"), "not_a_doi")


class CleanMarkupTests(unittest.TestCase):
    """测试 clean 函数对 JATS 标签、HTML 标签的处理与不等式保留。"""

    def test_clean_jats_tags(self):
        raw = "<jats:p>Sleep quality improved <jats:italic>slightly</jats:italic>.</jats:p>"
        self.assertEqual(main.clean(raw), "Sleep quality improved slightly.")

    def test_clean_html_entities(self):
        self.assertEqual(main.clean("A &amp; B <b>bold</b>"), "A & B bold")

    def test_clean_preserves_inequality(self):
        self.assertEqual(main.clean("If a<b, then c>d."), "If a<b, then c>d.")
        # 验证带空格的学术不等式不被误判为 HTML 标签
        self.assertEqual(
            main.clean("Findings showed p < 0.05 and HR > 1.2 in all cohorts."),
            "Findings showed p < 0.05 and HR > 1.2 in all cohorts.",
        )

    def test_clean_list_and_none(self):
        self.assertEqual(main.clean(None), "")
        self.assertEqual(main.clean(["Title A", "Title B"]), "Title A")



class ExtractTitleAndYearTests(unittest.TestCase):
    """测试 _extract_title 与 extract_year 的防御性数据解析。"""

    def test_extract_title_list(self):
        self.assertEqual(main._extract_title({"title": ["Quantum Gravity"]}), "Quantum Gravity")

    def test_extract_title_string(self):
        self.assertEqual(main._extract_title({"title": "Quantum Gravity"}), "Quantum Gravity")

    def test_extract_title_empty_or_none(self):
        self.assertEqual(main._extract_title({}), "Untitled")
        self.assertEqual(main._extract_title({"title": []}), "Untitled")
        self.assertEqual(main._extract_title({"title": [None, ""]}), "Untitled")
        self.assertEqual(main._extract_title(None), "Untitled")

    def test_extract_year_normal(self):
        item = {"published-print": {"date-parts": [[2023, 5, 1]]}}
        self.assertEqual(main.extract_year(item), "2023")

    def test_extract_year_fallback_to_online(self):
        item = {"published-online": {"date-parts": [[2024]]}}
        self.assertEqual(main.extract_year(item), "2024")

    def test_extract_year_corrupted_structure(self):
        self.assertEqual(main.extract_year({"published-print": None}), "")
        self.assertEqual(main.extract_year({"published-print": "not a dict"}), "")
        self.assertEqual(main.extract_year({"published-print": {"date-parts": []}}), "")
        self.assertEqual(main.extract_year(None), "")


class ClampMaxResultsTests(unittest.TestCase):
    """测试 clamp_max_results 的数值约束。"""

    def test_valid_and_bounds(self):
        self.assertEqual(main.clamp_max_results(5), 5)
        self.assertEqual(main.clamp_max_results(0), 1)
        self.assertEqual(main.clamp_max_results(-2), 1)
        self.assertEqual(main.clamp_max_results(20), 10)

    def test_types_and_overflow(self):
        self.assertEqual(main.clamp_max_results("8"), 8)
        self.assertEqual(main.clamp_max_results(None), 5)
        self.assertEqual(main.clamp_max_results(True), 5)
        self.assertEqual(main.clamp_max_results(False), 5)
        self.assertEqual(main.clamp_max_results(float("inf")), 5)


class EndpointTests(unittest.TestCase):
    """测试所有 FastAPI 端点的业务逻辑与异常处理。"""

    def test_health(self):
        self.assertEqual(_run(main.health()), {"status": "ok"})

    def test_tools(self):
        tools = _run(main.tools())
        self.assertIn("tools", tools)
        names = [t["name"] for t in tools["tools"]]
        self.assertIn("search_crossref_works", names)
        self.assertIn("get_crossref_work", names)
        self.assertIn("get_crossref_works_by_author", names)

    def test_manifest(self):
        manifest = _run(main.get_omi_tools_manifest())
        self.assertIn("tools", manifest)

    def test_search_crossref_works_success(self):
        mock_data = {
            "message": {
                "items": [
                    {
                        "title": ["Discovery of Gravitational Waves"],
                        "DOI": "10.1103/PhysRevLett.116.061102",
                        "published-print": {"date-parts": [[2016]]},
                    }
                ]
            }
        }
        with mock.patch.object(main, "crossref_get", return_value=mock_data):
            req = SearchWorksInput(query="gravitational waves", max_results=1)
            res = _run(main.search_crossref_works(req))
            self.assertIsNone(res.error)
            self.assertIn("Discovery of Gravitational Waves (2016)", res.result)
            self.assertIn("10.1103/PhysRevLett.116.061102", res.result)

    def test_search_crossref_works_short_query(self):
        req = SearchWorksInput(query="a")
        res = _run(main.search_crossref_works(req))
        self.assertEqual(res.error, "Query must be at least 2 characters.")

    def test_search_crossref_works_no_results(self):
        with mock.patch.object(main, "crossref_get", return_value={"message": {"items": []}}):
            req = SearchWorksInput(query="nonexistent_keyword_xyz")
            res = _run(main.search_crossref_works(req))
            self.assertIn("No Crossref results found for 'nonexistent_keyword_xyz'.", res.result)

    def test_search_crossref_works_http_error(self):
        mock_resp = types.SimpleNamespace(status_code=503)
        err = main.httpx.HTTPStatusError("Service Unavailable", response=mock_resp)
        with mock.patch.object(main, "crossref_get", side_effect=err):
            req = SearchWorksInput(query="quantum")
            res = _run(main.search_crossref_works(req))
            self.assertIn("Crossref API error: HTTP 503", res.error)

    def test_get_crossref_work_success_with_url(self):
        mock_data = {
            "message": {
                "title": ["Superconductivity at Room Temperature"],
                "publisher": "Nature Publishing Group",
                "DOI": "10.1038/nphys1170",
                "URL": "http://dx.doi.org/10.1038/nphys1170",
                "abstract": "<jats:p>We demonstrate novel superconductivity.</jats:p>",
                "published-print": {"date-parts": [[2020]]},
            }
        }
        with mock.patch.object(main, "crossref_get", return_value=mock_data) as mock_get:
            req = GetWorkInput(doi="https://doi.org/10.1038/nphys1170")
            res = _run(main.get_crossref_work(req))
            self.assertIsNone(res.error)
            self.assertIn("Title: Superconductivity at Room Temperature", res.result)
            self.assertIn("DOI: 10.1038/nphys1170", res.result)
            self.assertIn("Year: 2020", res.result)
            self.assertIn("Publisher: Nature Publishing Group", res.result)
            self.assertIn("Abstract: We demonstrate novel superconductivity.", res.result)
            # 确认请求路径清洗为标准编码的纯 DOI，而非包含 URL 前缀
            mock_get.assert_called_once_with("/works/10.1038%2Fnphys1170", {})

    def test_get_crossref_work_invalid_doi(self):
        req = GetWorkInput(doi="invalid-doi-without-slash")
        res = _run(main.get_crossref_work(req))
        self.assertEqual(res.error, "Invalid DOI format. Example: 10.1038/nphys1170")

    def test_get_crossref_work_path_traversal(self):
        req = GetWorkInput(doi="10.1038/../traversal")
        res = _run(main.get_crossref_work(req))
        self.assertEqual(res.error, "Invalid DOI value.")

    def test_get_crossref_work_not_found_404(self):
        mock_resp = types.SimpleNamespace(status_code=404)
        err = main.httpx.HTTPStatusError("Not Found", response=mock_resp)
        with mock.patch.object(main, "crossref_get", side_effect=err):
            req = GetWorkInput(doi="10.1000/182")
            res = _run(main.get_crossref_work(req))
            self.assertEqual(res.error, "Work not found for DOI: 10.1000/182")

    def test_get_crossref_works_by_author_success(self):
        mock_data = {
            "message": {
                "items": [
                    {
                        "title": ["Cosmological Frontiers"],
                        "DOI": "10.1088/1475-7516/2021/01/001",
                        "published-print": {"date-parts": [[2021]]},
                    }
                ]
            }
        }
        with mock.patch.object(main, "crossref_get", return_value=mock_data):
            req = AuthorWorksInput(author="Stephen Hawking", max_results=1)
            res = _run(main.get_crossref_works_by_author(req))
            self.assertIsNone(res.error)
            self.assertIn("Recent works for 'Stephen Hawking':", res.result)
            self.assertIn("Cosmological Frontiers (2021)", res.result)

    def test_search_crossref_works_none_message(self):
        # 当上游 message 为 None 或非字典时，不能抛 AttributeError
        with mock.patch.object(main, "crossref_get", return_value={"message": None}):
            req = SearchWorksInput(query="test_query")
            res = _run(main.search_crossref_works(req))
            self.assertIn("No Crossref results found for 'test_query'.", res.result)

    def test_get_crossref_work_non_doi_string(self):
        # 验证带斜杠但非 10. 开头的普通字符串被直接拦截
        req = GetWorkInput(doi="user/repo_not_a_doi")
        res = _run(main.get_crossref_work(req))
        self.assertEqual(res.error, "Invalid DOI format. Example: 10.1038/nphys1170")

    def test_validation_exception_handler(self):
        mock_exc = main.RequestValidationError([{"msg": "query is missing"}])
        res = _run(main.validation_exception_handler(None, mock_exc))
        self.assertEqual(res.status_code, 200)
        self.assertIn("Invalid request: query is missing", res.content["error"])

    def test_get_crossref_works_by_author_short_name(self):
        req = AuthorWorksInput(author="S")
        res = _run(main.get_crossref_works_by_author(req))
        self.assertEqual(res.error, "Author must be at least 2 characters.")

    def test_crossref_get_uses_pooled_client(self):
        mock_client = mock.MagicMock()
        mock_client.is_closed = False
        mock_resp = mock.MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"status": "ok", "message": {"items": []}}

        async def fake_get(url, params=None):
            return mock_resp

        mock_client.get = fake_get

        state = types.SimpleNamespace(client=mock_client)
        with mock.patch.object(main.app, "state", state, create=True):
            data = _run(main.crossref_get("/works", {"query": "test"}))
            self.assertEqual(data["status"], "ok")

    def test_crossref_get_fallback_when_client_none_or_closed(self):
        mock_resp = mock.MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"status": "fallback_ok"}

        async def fake_client_get(self, url, params=None):
            return mock_resp

        with mock.patch.object(main.httpx.AsyncClient, "get", fake_client_get):
            # 状态 1: client 为 None
            state_none = types.SimpleNamespace(client=None)
            with mock.patch.object(main.app, "state", state_none, create=True):
                data = _run(main.crossref_get("/works", {}))
                self.assertEqual(data["status"], "fallback_ok")

            # 状态 2: client 存在但 is_closed 为 True
            closed_client = types.SimpleNamespace(is_closed=True)
            state_closed = types.SimpleNamespace(client=closed_client)
            with mock.patch.object(main.app, "state", state_closed, create=True):
                data = _run(main.crossref_get("/works", {}))
                self.assertEqual(data["status"], "fallback_ok")

    def test_clean_jats_and_html_with_inequality(self):
        # 验证 JATS 标签与 HTML 实体剥离，同时保留学术不等式中的小于号
        raw_text = "<jats:p>We report x &lt; 0.5 in <jats:italic>Drosophila</jats:italic> &amp; mice.</jats:p>"
        cleaned = main.clean(raw_text)
        self.assertEqual(cleaned, "We report x < 0.5 in Drosophila & mice.")

    def test_get_work_jats_abstract_rendered_cleanly(self):
        mock_data = {
            "message": {
                "title": ["Genomic Variations"],
                "DOI": "10.1000/182",
                "publisher": "Science",
                "abstract": "<jats:sec><jats:p>Results show p &lt; 0.01 in <jats:italic>Drosophila</jats:italic>.</jats:p></jats:sec>",
                "issued": {"date-parts": [[2023]]},
            }
        }
        with mock.patch.object(main, "crossref_get", return_value=mock_data):
            req = GetWorkInput(doi="10.1000/182")
            res = _run(main.get_crossref_work(req))
            self.assertIsNone(res.error)
            self.assertIn("Abstract: Results show p < 0.01 in Drosophila.", res.result)
            self.assertNotIn("jats", res.result)

    def test_discovery_endpoints(self):
        health_res = _run(main.health())
        self.assertEqual(health_res, {"status": "ok"})

        tools_res = _run(main.tools())
        self.assertIn("tools", tools_res)
        self.assertEqual(len(tools_res["tools"]), 3)

        manifest_res = _run(main.get_omi_tools_manifest())
        self.assertIn("tools", manifest_res)
        self.assertEqual(len(manifest_res["tools"]), 3)


class FaceMarkupTests(unittest.TestCase):
    """验证 Crossref 字形排版标签（sub, sup, i, b, scp, font 等）剥离与不等号保护 (#14307, #14318)。"""

    def test_clean_strips_jats_paragraph_tags(self):
        raw = "<jats:p>Sleep quality improved <jats:italic>slightly</jats:italic>.</jats:p>"
        self.assertEqual(main.clean(raw), "Sleep quality improved slightly.")

    def test_clean_unescapes_entities_and_strips_generic_tags(self):
        self.assertEqual(main.clean("A &amp; B <b>bold</b>"), "A & B bold")

    def test_clean_preserves_inequality_operators(self):
        self.assertEqual(main.clean("If a<b, then c>d."), "If a<b, then c>d.")

    def test_clean_strips_closing_tags_after_word_chars(self):
        self.assertEqual(main.clean("text</p> tail"), "text tail")
        self.assertEqual(main.clean("A &amp; B <b>bold</b>"), "A & B bold")

    def test_clean_strips_word_adjacent_face_markup_tags(self):
        self.assertEqual(main.clean("H<sub>2</sub>O"), "H2O")
        self.assertEqual(main.clean("x<sup>y<sup>z</sup></sup>"), "xyz")
        self.assertEqual(main.clean("CO<sub>2</sub> emissions in 2020"), "CO2 emissions in 2020")
        self.assertEqual(main.clean("E=mc<sup>2</sup>"), "E=mc2")
        self.assertEqual(main.clean("Drug-A<sub>1</sub> and Drug-B<sup>2</sup>"), "Drug-A1 and Drug-B2")

    def test_clean_strips_face_markup_with_attributes(self):
        self.assertEqual(main.clean('<font color="red">Sample Title</font>'), "Sample Title")
        self.assertEqual(
            main.clean("<i>Italicized</i> species: <b>Escherichia coli</b>"),
            "Italicized species: Escherichia coli",
        )

    def test_clean_preserves_encoded_and_raw_inequalities(self):
        # 编码链式不等式必须保留 <b> 符号而非作为标签被吃掉 (#14307 review)
        self.assertEqual(main.clean("If a&lt;b&gt;c, continue."), "If a<b>c, continue.")
        self.assertEqual(main.clean("When x &lt; y and y &gt; z."), "When x < y and y > z.")


if __name__ == "__main__":
    unittest.main()
