# Convert conversations to standalone HTML report

Use this recipe to export Omi conversations and structured summaries into an elegant, self-contained HTML report that can be opened in any browser or shared with stakeholders.

Export conversations:

```sh
omi --json conversation list --limit 20 > conversations.json
```

Generate HTML report:

```sh
python conversations_to_html.py conversations.json report.html
```

Open `report.html` in your browser.
