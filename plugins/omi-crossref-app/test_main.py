"""Hermetic production-handler tests; framework models/routes are dependency doubles."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


def load_app():
    fastapi = ModuleType("fastapi")
    class FastAPI:
        def __init__(self, **kwargs):
            pass
        def get(self, *args, **kwargs):
            return lambda function: function
        post = get
    fastapi.FastAPI = FastAPI
    models = ModuleType("models")
    for name in ("AuthorWorksInput", "ChatToolResponse", "GetWorkInput", "SearchWorksInput"):
        setattr(models, name, SimpleNamespace)
    spec = importlib.util.spec_from_file_location("crossref_test_app", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"fastapi": fastapi, "httpx": ModuleType("httpx"), "models": models}):
        spec.loader.exec_module(module)
    return module


app = load_app()


class CrossrefAbstractTests(unittest.TestCase):
    def result(self, abstract):
        provider = AsyncMock(return_value={"message": {"DOI": "10.7554/eLife.45374", "abstract": abstract}})
        with patch.object(app, "crossref_get", provider):
            result = asyncio.run(app.get_crossref_work(SimpleNamespace(doi="10.7554/eLife.45374")))
        provider.assert_awaited_once_with("/works/10.7554%2FeLife.45374", {})
        return result.result

    def test_real_crossref_jats_abstract(self):
        # Public Crossref response, captured 2026-09-09; DOI 10.7554/eLife.45374.
        abstract = '<jats:p>A number of studies suggest that scientific papers with women in leading-author positions attract fewer citations than those with men in leading-author positions. We report the results of a matched case-control study of 1,269,542 papers in selected areas of medicine published between 2008 and 2014. We find that papers with female authors are, on average, cited between 6.5 and 12.6% less than papers with male authors. However, the standardized mean differences are very small, and the percentage overlaps between the distributions for male and female authors are extensive. Adjusting for self-citations, number of authors, international collaboration and journal prestige, we find near-identical per-paper citation impact for women and men in first and last author positions, with self-citations and journal prestige accounting for most of the small average differences. Our study demonstrates the importance of focusing greater attention on within-group variability and between-group overlap of distributions when interpreting and reporting results of gender-based comparisons of citation impact.</jats:p>'
        expected = abstract.removeprefix("<jats:p>").removesuffix("</jats:p>")
        self.assertEqual(self.result(abstract).split("Abstract: ", 1)[1], expected[:1200])

    def test_inline_blocks_and_literal_entities(self):
        cases = [
            ("<jats:p>First <jats:italic>part</jats:italic>.</jats:p><jats:p>Second.</jats:p>", "First part.\nSecond."),
            ("<p>A &amp; B: &lt;sample&gt; and x &lt; 2.</p>", "A & B: <sample> and x < 2."),
            ("<p>x<sub>i</sub><sup>2</sup> &gt; 0<br/>next</p>", "xi2 > 0\nnext"),
            ("<jats:p><mml:math><mml:mi>x</mml:mi><mml:mo>&lt;</mml:mo><mml:mn>2</mml:mn></mml:math></jats:p>", "x<2"),
            ("plain x < 2 &amp; y > 1", "plain x < 2 & y > 1"),
            ("<p>Unclosed <i>text", "Unclosed text"),
        ]
        for abstract, expected in cases:
            with self.subTest(abstract=abstract):
                self.assertEqual(self.result(abstract).split("Abstract: ", 1)[1], expected)

    def test_jats_break_preserves_word_boundary(self):
        for tag in ("break", "jats:break"):
            with self.subTest(tag=tag):
                abstract = f"<jats:p>one<{tag}/>two</jats:p>"
                self.assertEqual(self.result(abstract).split("Abstract: ", 1)[1], "one\ntwo")

    def test_cdata_preserves_literal_payload_before_truncation(self):
        cases = [
            ("<jats:p><![CDATA[A <sample> &amp; B]]></jats:p>", "A <sample> &amp; B"),
            ("<p>before <![CDATA[x < 2]]> after &amp; end</p>", "before x < 2 after & end"),
            ("<p><![CDATA[" + "x" * 1300 + "]]></p>", "x" * 1200),
        ]
        for abstract, expected in cases:
            with self.subTest(abstract=abstract[:80]):
                self.assertEqual(self.result(abstract).split("Abstract: ", 1)[1], expected)

    def test_cap_counts_visible_text_not_markup(self):
        abstract = "<p>" + "<i>a</i>" * 1300 + "</p>"
        self.assertEqual(self.result(abstract).split("Abstract: ", 1)[1], "a" * 1200)

    def test_upstream_raw_inequality_control(self):
        for abstract in ("If a<b, then c>d.", "If a<b and c>d."):
            with self.subTest(abstract=abstract):
                self.assertEqual(self.result(abstract).split("Abstract: ", 1)[1], abstract)

    def test_provider_error(self):
        with patch.object(app, "crossref_get", AsyncMock(side_effect=RuntimeError("offline"))):
            result = asyncio.run(app.get_crossref_work(SimpleNamespace(doi="10.7554/eLife.45374")))
        self.assertEqual(result.error, "Crossref request failed: offline")

    def test_missing_or_empty_abstract(self):
        for abstract in (None, "", "<jats:p> </jats:p>"):
            with self.subTest(abstract=abstract):
                self.assertNotIn("Abstract:", self.result(abstract))


if __name__ == "__main__":
    unittest.main()
