# Convert memories to CSV

Use this recipe to export saved memories from Omi into a spreadsheet-safe CSV file (UTF-8 with BOM, compatible with Excel, Google Sheets, and Numbers). It neutralizes spreadsheet formula injection risks and safely formats categories, tags, and timestamps.

Export memories:

```sh
omi --json memory list --limit 100 > memories.json
```

Convert to CSV:

```sh
python memories_to_csv.py memories.json memories.csv
```

## Schema Breakdown

The generated CSV contains the following fields matching the `DeveloperMemory` schema:

| Column | Description |
|---|---|
| `id` | Unique memory identifier |
| `content` | Stored memory text |
| `category` | Memory category (e.g. work, lifestyle, skills) |
| `visibility` | Privacy scope (`private` or `public`) |
| `tags` | JSON-encoded array of associated tags |
| `created_at` | Timestamp when the memory was captured |
