# Open Food Facts Omi Integration

Look up packaged food facts from Omi chat without connecting an account.

## What it does

- Search packaged foods by name
- Look up a product by barcode
- Compare up to five products by barcode
- Check listed allergens, traces, and ingredient text against foods a user wants to avoid
- Return nutrition per 100g, Nutri-Score, NOVA group, Eco-Score, labels, categories, ingredients, and product images when available

The app uses read-only Open Food Facts API calls. No OAuth or API key is required.

## Omi App Configuration

Use these values when creating the Omi app:

| Field | Value |
|-------|-------|
| Chat Tools Manifest URL | `https://YOUR-APP.up.railway.app/.well-known/omi-tools.json` |
| Setup URL | Leave blank |
| Setup Completed URL | Leave blank |

## Chat Tools

| Tool | Endpoint | Purpose |
|------|----------|---------|
| `search_foods` | `POST /tools/search_foods` | Search by product name |
| `lookup_barcode` | `POST /tools/lookup_barcode` | Look up one barcode |
| `compare_foods` | `POST /tools/compare_foods` | Compare up to five barcodes |
| `check_allergens` | `POST /tools/check_allergens` | Check a barcode or first search result against allergens to avoid |

## Example prompts

- "Look up barcode 737628064502."
- "Find oat milk and show sugar per 100g."
- "Compare these cereal barcodes."
- "Does this snack list milk, peanuts, or gluten?"

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Then open:

```text
http://localhost:8080/.well-known/omi-tools.json
```

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `OPENFOODFACTS_BASE_URL` | `https://world.openfoodfacts.org` | Use `https://world.openfoodfacts.net` for staging |
| `OPENFOODFACTS_USER_AGENT` | `OmiOpenFoodFactsApp/1.0 (https://github.com/BasedHardware/omi)` | Open Food Facts asks apps to identify themselves |
| `OPENFOODFACTS_TIMEOUT_SECONDS` | `8` | Request timeout |
| `PORT` | `8080` | Used by Railway and local runs |

## Data Notes

Open Food Facts is a community-contributed database. A missing allergen, nutrition field, or ingredient list does not prove the product is safe or complete. The app includes that caveat in tool responses so Omi does not present incomplete food data as a guarantee.

The search tool caps `page_size` at 10 to avoid turning chat use into a high-volume search client.
