"""Hermetic unit tests for Open Food Facts Omi Integration.

Runs with standard library unittest and hermetic stubs without requiring
external dependencies or live network access.
"""

import asyncio
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def load_app_modules(force_stubs: bool = True):
    """Load models and main modules hermetically without contaminating sys.modules.

    When force_stubs is True, stubs are installed unconditionally.
    """
    stubs = {}

    pydantic_mod = types.ModuleType("pydantic")

    class FieldInfoStub:
        def __init__(self, default=..., **kwargs):
            self.default = default
            self.ge = kwargs.get("ge")
            self.le = kwargs.get("le")
            self.min_length = kwargs.get("min_length")
            self.max_length = kwargs.get("max_length")

    class BaseModelStub:
        def __init__(self, **data):
            annotations = getattr(self.__class__, "__annotations__", {})
            for fname in annotations:
                if fname not in data and hasattr(self.__class__, fname):
                    attr_val = getattr(self.__class__, fname)
                    if isinstance(attr_val, FieldInfoStub):
                        if attr_val.default is not ...:
                            data[fname] = attr_val.default
                        else:
                            raise ValueError(f"Field '{fname}' is required.")
                    else:
                        data[fname] = attr_val

            for k, v in data.items():
                setattr(self, k, v)

            # Before validators
            for attr_name in dir(self.__class__):
                attr = getattr(self.__class__, attr_name)
                func = getattr(attr, "__func__", attr)
                if getattr(func, "_is_field_val", False):
                    target_field = getattr(func, "_target_field")
                    if hasattr(self, target_field):
                        try:
                            val = attr(getattr(self, target_field))
                        except TypeError:
                            val = func(self.__class__, getattr(self, target_field))
                        setattr(self, target_field, val)

            # Model validators
            for attr_name in dir(self.__class__):
                attr = getattr(self.__class__, attr_name)
                func = getattr(attr, "__func__", attr)
                if getattr(func, "_is_model_val", False):
                    try:
                        attr(self)
                    except TypeError:
                        func(self)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        def dict(self):
            return self.model_dump()

    def field_validator_stub(*fields, mode=None):
        def decorator(fn):
            actual_fn = getattr(fn, "__func__", fn)
            actual_fn._is_field_val = True
            actual_fn._target_field = fields[0]
            actual_fn._mode = mode
            return fn
        return decorator

    def model_validator_stub(mode=None):
        def decorator(fn):
            actual_fn = getattr(fn, "__func__", fn)
            actual_fn._is_model_val = True
            actual_fn._mode = mode
            return fn
        return decorator

    def Field_stub(default=..., **kwargs):
        return FieldInfoStub(default=default, **kwargs)

    pydantic_mod.BaseModel = BaseModelStub
    pydantic_mod.field_validator = field_validator_stub
    pydantic_mod.model_validator = model_validator_stub
    pydantic_mod.Field = Field_stub
    stubs["pydantic"] = pydantic_mod

    # httpx stub
    httpx_mod = types.ModuleType("httpx")

    class HTTPErrorStub(Exception):
        pass

    class RequestErrorStub(HTTPErrorStub):
        pass

    class HTTPStatusErrorStub(HTTPErrorStub):
        def __init__(self, message="", *, request=None, response=None):
            super().__init__(message)
            self.response = response or MagicMock(status_code=500)

    class AsyncClientStub:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def get(self, *args, **kwargs):
            return MagicMock()

        async def aclose(self):
            self.is_closed = True

    httpx_mod.HTTPError = HTTPErrorStub
    httpx_mod.RequestError = RequestErrorStub
    httpx_mod.HTTPStatusError = HTTPStatusErrorStub
    httpx_mod.AsyncClient = AsyncClientStub
    stubs["httpx"] = httpx_mod

    # fastapi stub
    fastapi_mod = types.ModuleType("fastapi")

    class FastAPIStub:
        def __init__(self, *args, **kwargs):
            self.state = types.SimpleNamespace()
            self._exception_handlers = {}

        def get(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        def post(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        def exception_handler(self, exc_class):
            def decorator(fn):
                self._exception_handlers[exc_class] = fn
                return fn
            return decorator

    class RequestStub:
        def __init__(self, json_data=None):
            self._json = json_data or {}

        async def json(self):
            return self._json

    fastapi_mod.FastAPI = FastAPIStub
    fastapi_mod.Request = RequestStub
    stubs["fastapi"] = fastapi_mod

    # exceptions stub
    exceptions_mod = types.ModuleType("fastapi.exceptions")

    class RequestValidationErrorStub(Exception):
        def __init__(self, errors=None):
            self._errors = errors or []

        def errors(self):
            return self._errors

    exceptions_mod.RequestValidationError = RequestValidationErrorStub
    stubs["fastapi.exceptions"] = exceptions_mod

    # responses stub
    responses_mod = types.ModuleType("fastapi.responses")

    class JSONResponseStub:
        def __init__(self, content, status_code=200):
            self.content = content
            self.status_code = status_code

    class HTMLResponseStub:
        def __init__(self, content, status_code=200):
            self.content = content
            self.status_code = status_code

    responses_mod.JSONResponse = JSONResponseStub
    responses_mod.HTMLResponse = HTMLResponseStub
    stubs["fastapi.responses"] = responses_mod

    # requests stub
    requests_mod = types.ModuleType("requests")

    class RequestsExceptionStub(Exception):
        pass

    requests_mod.RequestException = RequestsExceptionStub
    requests_mod.get = MagicMock()
    stubs["requests"] = requests_mod

    # starlette.concurrency stub
    starlette_concurrency_mod = types.ModuleType("starlette.concurrency")

    async def run_in_threadpool_stub(func, *args, **kwargs):
        return func(*args, **kwargs)

    starlette_concurrency_mod.run_in_threadpool = run_in_threadpool_stub
    stubs["starlette.concurrency"] = starlette_concurrency_mod

    old_modules = dict(sys.modules)
    for mod_name, mod_obj in stubs.items():
        sys.modules[mod_name] = mod_obj

    try:
        # Load models
        models_spec = importlib.util.spec_from_file_location(
            "test_openfoodfacts_models", os.path.join(PLUGIN_DIR, "models.py")
        )
        models_mod = importlib.util.module_from_spec(models_spec)
        models_spec.loader.exec_module(models_mod)

        # Load main
        main_spec = importlib.util.spec_from_file_location(
            "test_openfoodfacts_main", os.path.join(PLUGIN_DIR, "main.py")
        )
        main_mod = importlib.util.module_from_spec(main_spec)
        main_mod.models = models_mod
        main_spec.loader.exec_module(main_mod)
    finally:
        for mod_name in stubs:
            if mod_name in old_modules:
                sys.modules[mod_name] = old_modules[mod_name]
            else:
                sys.modules.pop(mod_name, None)

    return models_mod, main_mod


class TestOpenFoodFactsApp(unittest.TestCase):
    def setUp(self):
        self.models, self.main = load_app_modules(force_stubs=True)

    def test_search_foods_success(self):
        """Verify search_foods endpoint returns formatted products."""
        mock_payload = {
            "count": 1,
            "products": [
                {
                    "code": "3017620422003",
                    "product_name": "Nutella",
                    "brands": "Ferrero",
                    "quantity": "400g",
                    "nutriscore_grade": "e",
                    "nova_group": 4,
                    "ecoscore_grade": "d",
                    "allergens_tags": ["en:milk", "en:nuts"],
                    "traces_tags": ["en:soybeans"],
                    "labels_tags": ["en:green-dot"],
                    "categories_tags": ["en:spreads"],
                    "ingredients_text": "Sugar, palm oil, hazelnuts 13%, skimmed milk powder 8.7%, fat-reduced cocoa 7.4%.",
                    "nutriments": {"energy-kcal_100g": 539, "fat_100g": 30.9, "sugars_100g": 56.3},
                    "image_front_small_url": "https://images.openfoodfacts.org/nutella.jpg",
                }
            ],
        }

        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(return_value=mock_payload)):
            req = self.models.SearchFoodsRequest(query="nutella", page_size=5)
            resp = asyncio.run(self.main.tool_search_foods(req))
            self.assertTrue(resp.success)
            self.assertIn("Found 1 product(s)", resp.message)
            self.assertIn("products", resp.data)
            self.assertEqual(len(resp.data["products"]), 1)
            prod = resp.data["products"][0]
            self.assertEqual(prod["name"], "Nutella")
            self.assertEqual(prod["barcode"], "3017620422003")
            self.assertEqual(prod["nutri_score"], "E")
            self.assertEqual(prod["nova_group"], 4)
            self.assertEqual(prod["eco_score"], "D")
            self.assertEqual(prod["allergens"], ["milk", "nuts"])
            self.assertEqual(prod["traces"], ["soybeans"])
            self.assertEqual(prod["nutrition_per_100g"]["fat_g"], 30.9)

    def test_search_foods_empty(self):
        """Verify search_foods handles empty results gracefully."""
        mock_payload = {"count": 0, "products": []}
        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(return_value=mock_payload)):
            req = self.models.SearchFoodsRequest(query="nonexistentfoodquery999")
            resp = asyncio.run(self.main.tool_search_foods(req))
            self.assertTrue(resp.success)
            self.assertIn("No Open Food Facts products found", resp.message)
            self.assertEqual(len(resp.data["products"]), 0)

    def test_search_foods_page_size_clamping(self):
        """Verify page_size clamping logic."""
        self.assertEqual(self.models.clamp_page_size(-5), 1)
        self.assertEqual(self.models.clamp_page_size(0), 1)
        self.assertEqual(self.models.clamp_page_size(5), 5)
        self.assertEqual(self.models.clamp_page_size(25), 10)
        self.assertEqual(self.models.clamp_page_size("invalid"), 5)

    def test_lookup_barcode_success(self):
        """Verify lookup_barcode returns product details."""
        mock_payload = {
            "status": 1,
            "product": {
                "code": "737628064502",
                "product_name": "Thai Peanut Noodles",
                "nutriscore_grade": "c",
                "nutriments": {"energy-kcal_100g": 380, "proteins_100g": 12.0},
            },
        }
        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(return_value=mock_payload)):
            req = self.models.LookupBarcodeRequest(barcode="737628064502")
            resp = asyncio.run(self.main.tool_lookup_barcode(req))
            self.assertTrue(resp.success)
            self.assertIn("Thai Peanut Noodles found", resp.message)
            self.assertEqual(resp.data["product"]["barcode"], "737628064502")
            self.assertEqual(resp.data["product"]["nutrition_per_100g"]["proteins_g"], 12.0)

    def test_lookup_barcode_not_found(self):
        """Verify lookup_barcode handles missing barcode (status 0)."""
        mock_payload = {"status": 0, "product": None}
        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(return_value=mock_payload)):
            req = self.models.LookupBarcodeRequest(barcode="0000000000000")
            resp = asyncio.run(self.main.tool_lookup_barcode(req))
            self.assertFalse(resp.success)
            self.assertIn("no product found", resp.message)

    def test_lookup_barcode_cleaning(self):
        """Verify clean_barcode extracts digits only."""
        self.assertEqual(self.models.clean_barcode("123-456 789"), "123456789")
        self.assertEqual(self.models.clean_barcode("barcode: 9988"), "9988")
        self.assertEqual(self.models.clean_barcode("abc"), "")

    def test_compare_foods_success(self):
        """Verify compare_foods compares multiple barcodes."""
        def mock_lookup(path, params=None):
            if "111" in path:
                return {"status": 1, "product": {"code": "111", "product_name": "Food A"}}
            return {"status": 1, "product": {"code": "222", "product_name": "Food B"}}

        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(side_effect=mock_lookup)):
            req = self.models.CompareFoodsRequest(barcodes=["111", "222"])
            resp = asyncio.run(self.main.tool_compare_foods(req))
            self.assertTrue(resp.success)
            self.assertIn("Compared 2 product(s)", resp.message)
            self.assertEqual(len(resp.data["products"]), 2)

    def test_compare_foods_partial_error(self):
        """Verify compare_foods handles one valid and one missing barcode."""
        def mock_lookup(path, params=None):
            if "111" in path:
                return {"status": 1, "product": {"code": "111", "product_name": "Food A"}}
            return {"status": 0, "product": None}

        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(side_effect=mock_lookup)):
            req = self.models.CompareFoodsRequest(barcodes=["111", "999"])
            resp = asyncio.run(self.main.tool_compare_foods(req))
            self.assertTrue(resp.success)
            self.assertEqual(len(resp.data["products"]), 1)
            self.assertEqual(len(resp.data["errors"]), 1)

    def test_check_allergens_by_barcode_positive(self):
        """Verify check_allergens detects allergen from barcode lookup."""
        mock_payload = {
            "status": 1,
            "product": {
                "code": "12345",
                "product_name": "Almond Granola",
                "allergens_tags": ["en:nuts", "en:gluten"],
                "traces_tags": [],
                "ingredients_text": "Rolled oats, almonds, honey.",
            },
        }
        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(return_value=mock_payload)):
            req = self.models.CheckAllergensRequest(barcode="12345", avoid=["nuts", "soy"])
            resp = asyncio.run(self.main.tool_check_allergens(req))
            self.assertTrue(resp.success)
            self.assertIn("may include: nuts", resp.message)
            self.assertEqual(resp.data["matches"], ["nuts"])

    def test_check_allergens_by_query_positive(self):
        """Verify check_allergens detects allergen from product search."""
        mock_search = {
            "count": 1,
            "products": [
                {
                    "code": "54321",
                    "product_name": "Soy Milk",
                    "allergens_tags": ["en:soybeans"],
                    "traces_tags": [],
                    "ingredients_text": "Water, soybeans, sugar.",
                }
            ],
        }
        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(return_value=mock_search)):
            req = self.models.CheckAllergensRequest(query="soy milk", avoid=["soybeans"])
            resp = asyncio.run(self.main.tool_check_allergens(req))
            self.assertTrue(resp.success)
            self.assertIn("may include: soybeans", resp.message)
            self.assertEqual(resp.data["matches"], ["soybeans"])

    def test_check_allergens_negative(self):
        """Verify check_allergens returns safe notice when no allergens match."""
        mock_payload = {
            "status": 1,
            "product": {
                "code": "11111",
                "product_name": "Apple Juice",
                "allergens_tags": [],
                "traces_tags": [],
                "ingredients_text": "Apples, water.",
            },
        }
        with patch.object(self.main, "_openfoodfacts_get_async", AsyncMock(return_value=mock_payload)):
            req = self.models.CheckAllergensRequest(barcode="11111", avoid=["peanuts", "milk"])
            resp = asyncio.run(self.main.tool_check_allergens(req))
            self.assertTrue(resp.success)
            self.assertIn("No listed match found", resp.message)
            self.assertEqual(resp.data["matches"], [])

    def test_ingredient_mentions_term_exclusions(self):
        """Verify _ingredient_mentions_term handles -free, no, and word boundaries."""
        fn = self.main._ingredient_mentions_term
        self.assertFalse(fn("Made with gluten-free oat flour.", "gluten"))
        self.assertFalse(fn("Certified gluten free oats.", "gluten"))
        self.assertFalse(fn("Contains no dairy ingredients.", "dairy"))
        self.assertFalse(fn("100% non-dairy beverage.", "dairy"))
        self.assertTrue(fn("Contains dairy and wheat.", "dairy"))
        self.assertTrue(fn("Contains wheat flour.", "wheat"))
        self.assertFalse(fn("", "wheat"))
        self.assertFalse(fn("Text", ""))

    def test_nutrient_per_100g_and_non_dict_guard(self):
        """Verify _nutrient only returns per-100g and guards non-dict nutriments."""
        # Non-dict product
        self.assertIsNone(self.main._nutrient(None, "fat"))
        self.assertIsNone(self.main._nutrient("not a dict", "fat"))

        # Non-dict nutriments
        prod_bad_nutr = {"nutriments": "invalid"}
        self.assertIsNone(self.main._nutrient(prod_bad_nutr, "fat"))

        # Serving-only does not leak to per 100g
        prod_serving = {"nutriments": {"fat": 10.0}}
        self.assertIsNone(self.main._nutrient(prod_serving, "fat"))

        # per-100g key present
        prod_per_100g = {"nutriments": {"fat_100g": 2.5}}
        self.assertEqual(self.main._nutrient(prod_per_100g, "fat"), 2.5)

    def test_summarize_product_defensive(self):
        """Verify _summarize_product handles non-dict, non-string grades, and nulls."""
        # Non-dict
        empty_sum = self.main._summarize_product(None)
        self.assertEqual(empty_sum["name"], "Unknown product")
        self.assertIsNone(empty_sum["nutri_score"])

        # Non-string nutriscore and ecoscore
        weird_prod = {
            "product_name": "Test Item",
            "nutriscore_grade": 123,
            "ecoscore_grade": False,
            "nova_group": "unknown",
            "allergens_tags": None,
        }
        res = self.main._summarize_product(weird_prod)
        self.assertEqual(res["name"], "Test Item")
        self.assertEqual(res["nutri_score"], "123")
        self.assertEqual(res["eco_score"], "FALSE")
        self.assertIsNone(res["nova_group"])
        self.assertEqual(res["allergens"], [])

    def test_normalize_tag_defensive(self):
        """Verify _normalize_tag handles non-string tags."""
        self.assertEqual(self.main._normalize_tag(None), "")
        self.assertEqual(self.main._normalize_tag(123), "")
        self.assertEqual(self.main._normalize_tag("en:tree-nuts"), "tree nuts")
        self.assertEqual(self.main._normalize_tags([1, "en:soy", None]), ["soy"])

    def test_validation_exception_handler(self):
        """Verify validation_exception_handler converts 422 to 200 JSON envelope."""
        exc = self.main.RequestValidationError([
            {"loc": ["body", "query"], "msg": "query cannot be empty", "type": "value_error"}
        ])
        req = self.main.Request()
        resp = asyncio.run(self.main.validation_exception_handler(req, exc))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.content["success"])
        self.assertIn("query: query cannot be empty", resp.content["message"])

    def test_health_and_manifest_endpoints(self):
        """Verify health check and tool manifest endpoints."""
        health = asyncio.run(self.main.health())
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["service"], "omi-openfoodfacts-app")

        manifest = asyncio.run(self.main.get_omi_tools_manifest())
        self.assertIn("tools", manifest)
        tool_names = [t["name"] for t in manifest["tools"]]
        self.assertIn("search_foods", tool_names)
        self.assertIn("lookup_barcode", tool_names)
        self.assertIn("compare_foods", tool_names)
        self.assertIn("check_allergens", tool_names)

        alias = asyncio.run(self.main.get_manifest_alias())
        self.assertEqual(alias, manifest)

    def test_lifespan_client_fallback(self):
        """Verify fallback when app.state.http_client is None."""
        client = asyncio.run(self.main._get_client(None))
        self.assertIsNotNone(client)

    def test_openfoodfacts_get_async_error_handling(self):
        """Verify _openfoodfacts_get_async handles non-dict response."""
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_resp = MagicMock()
        mock_resp.json.return_value = ["not a dict"]
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch.object(self.main, "_get_client", AsyncMock(return_value=mock_client)):
            data = asyncio.run(self.main._openfoodfacts_get_async("/test"))
            self.assertIn("error", data)
            self.assertIn("non-dictionary", data["error"])

    def test_real_pydantic_if_installed(self):
        """Verify real Pydantic behavior if installed."""
        try:
            import pydantic
            models_mod, _ = load_app_modules(force_stubs=False)
            # Valid search
            req = models_mod.SearchFoodsRequest(query="  cereal  ", page_size=20)
            self.assertEqual(req.query, "cereal")
            self.assertEqual(req.page_size, 10)

            # Valid barcode
            bc = models_mod.LookupBarcodeRequest(barcode="  0123-456  ")
            self.assertEqual(bc.barcode, "0123456")

            # Valid check allergens
            ca = models_mod.CheckAllergensRequest(barcode="123", avoid=[" dairy "])
            self.assertEqual(ca.avoid, ["dairy"])
            self.assertEqual(ca.barcode, "123")
        except ImportError:
            pass


if __name__ == "__main__":
    unittest.main()
