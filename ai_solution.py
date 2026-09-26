```python
import csv
import omi.client as client

def main():
    # Initialize the OMI client with the API key
    client.initialize(
        api_key_path="config/omi.yaml",
        config_required=True,
        enable_omi_apis=True,
    )

    # Get the action items
    action_items = client.get_action_items().action_items

    # Define the CSV field names
    field_names = ["Id", "Title", "Description", "CreatedAt", "UpdatedAt"]

    # Write to CSV
    with open("action_items.csv", "w", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, field_names)
        writer.writeheader()
        for action_item in action_items:
            writer.writerow({
                "Id": action_item.id,
                "Title": action_item.title,
                "Description": action_item.description,
                "CreatedAt": action_item.created_at,
                "UpdatedAt": action_item.updated_at
            })

if __name__ == "__main__":
    main()
```