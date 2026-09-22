# Convert goals to CSV

Use this recipe to export goals from Omi into a spreadsheet-safe CSV file (UTF-8 with BOM, compatible with Excel, Google Sheets, and Numbers). It extracts goal titles, descriptions, target dates (`horizon_at`), and current progress against targets (`current_value` / `target_value`), while neutralizing formula injection risks.

Export goals:

```sh
omi --json goal list --limit 100 > goals.json
```

Convert to CSV:

```sh
python goals_to_csv.py goals.json goals.csv
```

## Schema Breakdown

The generated CSV contains the following columns populated from the Omi Goal schema:

| Column | Source Field | Description |
|---|---|---|
| `id` | `id` | Unique goal identifier |
| `title` | `title` | Goal headline / title |
| `description` | `description` | Detailed goal description |
| `target_date` | `horizon_at` | Completion target date / timeframe |
| `progress` | `current_value` / `target_value` | Current numerical progress formatted with unit metric |
| `created_at` | `created_at` | Timestamp when the goal was created |
