# Convert screen history to CSV

Use this recipe to export local desktop screen history queries from Omi into a spreadsheet-safe CSV file (UTF-8 with BOM, compatible with Excel, Google Sheets, and Numbers). It neutralizes spreadsheet formula injection risks and safely flattens window titles, OCR transcripts, and timestamps.

Export screen history via the local desktop CLI:

```sh
omi --json local search-screen "pricing page" --days 7 > screen_history.json
```

Convert to CSV:

```sh
python screen_history_to_csv.py screen_history.json screen_history.csv
```


## Privacy Considerations
Screen history exports may contain sensitive on-screen information (passwords, private messages, personal data). Store exported CSV files in secure locations with appropriate access controls and avoid committing raw exports to public repositories.
