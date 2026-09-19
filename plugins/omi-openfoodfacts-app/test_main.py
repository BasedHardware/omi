"""Hermetic Open Food Facts plugin regressions (#13987).

Imports the production module with framework-only stubs (fastapi, pydantic,
httpx, requests, starlette), then exercises the real parsers, typed request
models, tool handlers, and the pooled-client/fallback HTTP seam. No network,
credentials, or third-party runtime packages are required.

Run with: python3 plugins/omi-openfoodfacts-app/test_main.py
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


def _stub_modules():
    class FastAPI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.state = SimpleNamespace()

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def exception_handler(self, *args, **kwargs):
            return lambda handler: handler

    class Request:
        pass

    class RequestValidationError(Exception):
        def __init__(self, errors=None):
            super().__init__("request validation failed")
            self._errors = errors or []

        def errors(self):
            return self._errors

    class JSONResponse:
        def __init__(self, content=None, status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code

    class BaseModel:
        """Applies declared field defaults like pydantic, without validation."""

        def __init__(self, **kwargs):
            for name in getattr(type(self), "__annotations__", {}):
                setattr(self, name, getattr(type(self), name, None))
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self, *args, **kwargs):
            return dict(self.__dict__)

        def dict(self, *args, **kwargs):
            return self.model_dump()

    class RequestException(Exception):
        pass

    def _blocked_get(*args, **kwargs):
        raise RequestException("hermetic test stub: no network")

    requests = ModuleType("requests")
    requests.RequestException = RequestException
    requests.get = _blocked_get

    class HTTPError(Exception):
        pass

    class AsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            await self.aclose()
            return False

        async def get(self, *args, **kwargs):
            raise HTTPError("hermetic test stub: no network")

        async def aclose(self):
            self.closed = True

    httpx = ModuleType("httpx")
    httpx.AsyncClient = AsyncClient
    httpx.HTTPError = HTTPError
    httpx.TimeoutException = type("TimeoutException", (HTTPError,), {})

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi_exceptions = ModuleType("fastapi.exceptions")
    fastapi_exceptions.RequestValidationError = RequestValidationError
    fastapi_responses = ModuleType("fastapi.responses")
    fastapi_responses.JSONResponse = JSONResponse
    fastapi.exceptions = fastapi_exceptions
    fastapi.responses = fastapi_responses

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    async def run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    starlette = ModuleType("starlette")
    starlette_concurrency = ModuleType("starlette.concurrency")
    starlette_concurrency.run_in_threadpool = run_in_threadpool
    starlette.concurrency = starlette_concurrency

    return {
        "fastapi": fastapi,
        "fastapi.exceptions": fastapi_exceptions,
        "fastapi.responses": fastapi_responses,
        "pydantic": pydantic,
        "requests": requests,
        "starlette": starlette,
        "starlette.concurrency": starlette_concurrency,
        "httpx": httpx,
    }


def load_app():
    plugin_dir = Path(__file__).resolve().parent
    stubs = _stub_modules()

    models_path = plugin_dir / "models.py"
    if models_path.exists():
        spec = importlib.util.spec_from_file_location("models", models_path)
        models_module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(models_module)
        stubs["models"] = models_module

    spec = importlib.util.spec_from_file_location(
        "openfoodfacts_app", plugin_dir / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_app()


def _product(**overrides):
    product = {"code": "1", "product_name": "Oat milk"}
    product.update(overrides)
    return product


class SummarizeProductTests(unittest.TestCase):
    """Non-string grade fields must not raise AttributeError (#13987)."""

    def test_numeric_nutriscore_grade_returns_none_instead_of_crashing(self):
        summary = app._summarize_product(_product(nutriscore_grade=2))
        self.assertIsNone(summary["nutri_score"])

    def test_boolean_ecoscore_grade_returns_none_instead_of_crashing(self):
        summary = app._summarize_product(_product(ecoscore_grade=True))
        self.assertIsNone(summary["eco_score"])

    def test_dict_and_list_grades_return_none(self):
        summary = app._summarize_product(
            _product(nutriscore_grade={"grade": "a"}, ecoscore_grade=["b"])
        )
        self.assertIsNone(summary["nutri_score"])
        self.assertIsNone(summary["eco_score"])

    def test_string_grades_are_uppercased(self):
        summary = app._summarize_product(
            _product(nutriscore_grade="a", ecoscore_grade=" b ")
        )
        self.assertEqual(summary["nutri_score"], "A")
        self.assertEqual(summary["eco_score"], "B")

    def test_numeric_code_and_ingredients_are_coerced(self):
        summary = app._summarize_product(_product(code=123, ingredients_text=42))
        self.assertEqual(summary["barcode"], "123")
        self.assertEqual(summary["ingredients"], "42")


class NutrientTests(unittest.TestCase):
    """Non-dict nutriments must not raise TypeError or leak substring hits."""

    def test_string_nutriments_does_not_leak_substring_match(self):
        # "fat_100g" in "fat_100g" is True for strings; must never index it.
        self.assertIsNone(app._nutrient({"nutriments": "fat_100g"}, "fat"))

    def test_list_nutriments_returns_none(self):
        self.assertIsNone(app._nutrient({"nutriments": ["fat_100g"]}, "fat"))

    def test_scalar_nutriments_returns_none(self):
        self.assertIsNone(app._nutrient({"nutriments": 7}, "fat"))

    def test_per_100g_key_is_returned(self):
        product = {"nutriments": {"fat_100g": 0.2, "fat": 1.5}}
        self.assertEqual(app._nutrient(product, "fat"), 0.2)

    def test_serving_only_nutrient_not_reported_as_per_100g(self):
        summary = app._summarize_product(_product(nutriments={"fat": 1.5}))
        self.assertIsNone(summary["nutrition_per_100g"]["fat_g"])


class SearchAndLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_filters_non_dict_products(self):
        async def fake_get(path, params=None):
            return {
                "products": [None, "junk", 5, _product()],
                "count": 4,
            }

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            result = await app._search_foods("oat", 5)
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["products"][0]["name"], "Oat milk")

    async def test_search_non_list_products_yields_empty_list(self):
        async def fake_get(path, params=None):
            return {"products": {"unexpected": "shape"}, "count": 1}

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            result = await app._search_foods("oat", 5)
        self.assertEqual(result["products"], [])

    async def test_search_non_dict_payload_returns_error(self):
        async def fake_get(path, params=None):
            return ["not", "a", "dict"]

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            result = await app._search_foods("oat", 5)
        self.assertIn("error", result)

    async def test_lookup_non_dict_product_returns_error(self):
        async def fake_get(path, params=None):
            return {"status": 1, "product": "not-a-dict"}

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            result = await app._lookup_barcode("12345")
        self.assertIn("error", result)
        self.assertIn("no product found", result["error"])

    async def test_lookup_blank_barcode_short_circuits_before_http(self):
        called = []

        async def fake_get(path, params=None):
            called.append(path)
            return {}

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            result = await app._lookup_barcode("  abc ")
        self.assertEqual(result["error"], "barcode is required")
        self.assertEqual(called, [])

    async def test_search_uses_cgi_fulltext_endpoint(self):
        captured = {}

        async def fake_get(path, params=None):
            captured["path"] = path
            captured["params"] = params or {}
            return {"products": [_product()], "count": 1}

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            result = await app._search_foods("oat milk", 5)
        self.assertEqual(captured["path"], "/cgi/search.pl")
        self.assertEqual(captured["params"]["search_terms"], "oat milk")
        self.assertEqual(captured["params"]["json"], 1)
        self.assertEqual(result["count"], 1)


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_endpoint_success_envelope(self):
        async def fake_get(path, params=None):
            return {"products": [_product()], "count": 1}

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            response = await app.tool_search_foods(
                app.SearchFoodsRequest(query="oat", page_size=5)
            )
        self.assertTrue(response.success)
        self.assertIn("Found 1 product", response.message)
        self.assertEqual(response.data["products"][0]["name"], "Oat milk")

    async def test_search_endpoint_blank_query_returns_error_envelope(self):
        response = await app.tool_search_foods(app.SearchFoodsRequest(query="   "))
        self.assertFalse(response.success)
        self.assertIn("query is required", response.message)

    async def test_search_endpoint_clamps_page_size(self):
        captured = {}

        async def fake_get(path, params=None):
            captured.update(params or {})
            return {"products": [], "count": 0}

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            await app.tool_search_foods(
                app.SearchFoodsRequest(query="oat", page_size=99)
            )
        self.assertEqual(captured["page_size"], 10)

    async def test_lookup_endpoint_success(self):
        async def fake_get(path, params=None):
            return {
                "status": 1,
                "product": {"code": "737628064502", "product_name": "Peanut butter"},
            }

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            response = await app.tool_lookup_barcode(
                app.LookupBarcodeRequest(barcode="737628064502")
            )
        self.assertTrue(response.success)
        self.assertIn("Peanut butter", response.message)

    async def test_compare_rejects_non_list_barcodes(self):
        response = await app.tool_compare_foods(
            app.CompareFoodsRequest(barcodes="123")
        )
        self.assertFalse(response.success)
        self.assertIn("barcodes must be a list", response.message)

    async def test_compare_reports_per_barcode_errors(self):
        async def fake_get(path, params=None):
            if "111" in path:
                return {
                    "status": 1,
                    "product": {"code": "111", "product_name": "Bar"},
                }
            return {"status": 0}

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            response = await app.tool_compare_foods(
                app.CompareFoodsRequest(barcodes=["111", "999"])
            )
        self.assertTrue(response.success)
        self.assertEqual(len(response.data["products"]), 1)
        self.assertEqual(response.data["errors"][0]["barcode"], "999")

    async def test_check_allergens_requires_non_empty_avoid(self):
        response = await app.tool_check_allergens(
            app.CheckAllergensRequest(barcode="123", avoid="milk")
        )
        self.assertFalse(response.success)
        self.assertIn("avoid must be a non-empty list", response.message)

    async def test_check_allergens_requires_barcode_or_query(self):
        response = await app.tool_check_allergens(
            app.CheckAllergensRequest(avoid=["milk"])
        )
        self.assertFalse(response.success)
        self.assertIn("barcode or a query", response.message)

    async def test_check_allergens_matches_listed_allergen(self):
        async def fake_get(path, params=None):
            return {
                "status": 1,
                "product": _product(
                    product_name="Cereal",
                    allergens_tags=["en:milk", "en:gluten"],
                ),
            }

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            response = await app.tool_check_allergens(
                app.CheckAllergensRequest(barcode="123", avoid=["Milk", "peanuts"])
            )
        self.assertTrue(response.success)
        self.assertEqual(response.data["matches"], ["milk"])
        self.assertIn("may include: milk", response.message)

    async def test_check_allergens_ignores_milk_free_ingredient_text(self):
        async def fake_get(path, params=None):
            return {
                "status": 1,
                "product": _product(ingredients_text="milk-free oat drink"),
            }

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            response = await app.tool_check_allergens(
                app.CheckAllergensRequest(barcode="123", avoid=["milk"])
            )
        self.assertTrue(response.success)
        self.assertEqual(response.data["matches"], [])

    async def test_check_allergens_via_query_path(self):
        async def fake_get(path, params=None):
            return {
                "products": [
                    _product(product_name="Trail mix", traces_tags=["en:peanuts"])
                ],
                "count": 1,
            }

        with patch.object(app, "_openfoodfacts_get_async", fake_get):
            response = await app.tool_check_allergens(
                app.CheckAllergensRequest(query="trail mix", avoid=["peanuts"])
            )
        self.assertTrue(response.success)
        self.assertEqual(response.data["matches"], ["peanuts"])


class ValidationHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_validation_error_returns_200_envelope(self):
        class FakeValidationError:
            def errors(self):
                return [{"loc": ("body", "query"), "msg": "field required"}]

        response = await app.validation_exception_handler(None, FakeValidationError())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.content["success"])
        self.assertIn("query", response.content["message"])

    async def test_validation_handler_tolerates_unusual_error_shape(self):
        class WeirdError:
            def errors(self):
                raise RuntimeError("nope")

        response = await app.validation_exception_handler(None, WeirdError())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.content["success"])


class PooledClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        app.app.state.http_client = None

    async def test_uses_pooled_client_when_set(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"hello": "world"}

        class FakeClient:
            def __init__(self):
                self.calls = []

            async def get(self, path, params=None):
                self.calls.append((path, params))
                return FakeResponse()

        client = FakeClient()
        app.app.state.http_client = client
        result = await app._openfoodfacts_get_async("/x", {"a": 1})
        self.assertEqual(result, {"hello": "world"})
        self.assertEqual(client.calls, [("/x", {"a": 1})])

    async def test_pooled_client_error_returns_error_envelope(self):
        class FailingClient:
            async def get(self, *args, **kwargs):
                raise RuntimeError("conn reset")

        app.app.state.http_client = FailingClient()
        result = await app._openfoodfacts_get_async("/x")
        self.assertIn("conn reset", result["error"])

    async def test_pooled_client_non_json_returns_error(self):
        class BadJsonResponse:
            def raise_for_status(self):
                pass

            def json(self):
                raise ValueError("no json")

        class Client:
            async def get(self, *args, **kwargs):
                return BadJsonResponse()

        app.app.state.http_client = Client()
        result = await app._openfoodfacts_get_async("/x")
        self.assertEqual(
            result["error"], "Open Food Facts returned a non-JSON response"
        )

    async def test_falls_back_to_threadpool_without_pooled_client(self):
        app.app.state.http_client = None

        def fake_sync_get(path, params=None):
            return {"via": "threadpool", "path": path}

        with patch.object(app, "_openfoodfacts_get", fake_sync_get):
            result = await app._openfoodfacts_get_async("/y", {"b": 2})
        self.assertEqual(result["via"], "threadpool")
        self.assertEqual(result["path"], "/y")

    async def test_lifespan_installs_and_closes_pooled_client(self):
        app.app.state.http_client = None
        async with app.lifespan(app.app):
            client = app.app.state.http_client
            self.assertIsNotNone(client)
        self.assertTrue(client.closed)


class EnvelopeTests(unittest.TestCase):
    def test_fail_envelope_carries_error_data(self):
        response = app.ChatToolResponse.fail("boom")
        self.assertFalse(response.success)
        self.assertEqual(response.message, "boom")
        self.assertEqual(response.data["error"], "boom")

    def test_as_dict_serializes_envelope(self):
        payload = app.ChatToolResponse.ok("hi", {"x": 1}).as_dict()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"], {"x": 1})


class IngredientMentionTests(unittest.TestCase):
    def test_free_suffix_is_not_a_match(self):
        self.assertFalse(app._ingredient_mentions_term("milk-free oats", "milk"))
        self.assertFalse(app._ingredient_mentions_term("gluten free oats", "gluten"))

    def test_negated_mention_is_not_a_match(self):
        self.assertFalse(app._ingredient_mentions_term("no milk added", "milk"))

    def test_plain_mention_matches(self):
        self.assertTrue(app._ingredient_mentions_term("oats, milk, sugar", "milk"))

    def test_embedded_substring_does_not_match(self):
        self.assertFalse(
            app._ingredient_mentions_term("buttermilkshake powder", "milk")
        )


class RequestModelTests(unittest.TestCase):
    def test_clamped_page_size_bounds(self):
        self.assertEqual(app.SearchFoodsRequest(page_size=99).clamped_page_size(), 10)
        self.assertEqual(app.SearchFoodsRequest(page_size=0).clamped_page_size(), 1)
        self.assertEqual(
            app.SearchFoodsRequest(page_size="junk").clamped_page_size(), 5
        )

    def test_clean_query_trims(self):
        self.assertEqual(app.SearchFoodsRequest(query="  oat  ").clean_query(), "oat")
        self.assertEqual(app.SearchFoodsRequest(query=None).clean_query(), "")

    def test_check_allergens_target_error(self):
        self.assertIsNotNone(
            app.CheckAllergensRequest(avoid=["milk"]).target_error()
        )
        self.assertIsNone(
            app.CheckAllergensRequest(barcode="1", avoid=["milk"]).target_error()
        )
        self.assertIsNone(
            app.CheckAllergensRequest(query="x", avoid=["milk"]).target_error()
        )

    def test_clean_avoid_normalizes_terms(self):
        request = app.CheckAllergensRequest(avoid=[" Milk ", 5, " "])
        self.assertEqual(request.clean_avoid(), ["Milk", "5"])


if __name__ == "__main__":
    unittest.main()
