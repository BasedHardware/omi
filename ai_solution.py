```python
def _openfoodfacts_get(*args, **kwargs) -> dict:
    """
    Helper to get data from Open Food Facts.
    """
    try:
        response = requests.get(
            url=f"{API_ENDPOINT}product.json",
            params=kwargs,
            headers=HEADERS,
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as exc:
        _log_error(str(exc))
        return {
            "error": {"code": 500, "message": _("An error occurred. Please try again later.")}
        }
```