#!/usr/bin/env python3
"""
Standalone script to export OMI action items to CSV.
Prevents formula injection and uses UTF-8-sig encoding for Excel compatibility.
"""
import csv
import os
from omi import OMI

def main():
    # Fetch OMI token from environment
    token = os.environ.get("OMI_TOKEN")
    if not token:
        raise ValueError("OMI_TOKEN environment variable not set")

    # Initialize OMI client
    client = OMI(token=token)

    # Fetch action items
    action_items = client.action_items.list()

    # Prepare CSV data
    headers = ["id", "title", "description", "created_at", "status"]
    rows = []
    
    for item in action_items:
        # Escape potential formula content by wrapping in quotes
        rows.append([
            item.id,
            f'"{item.title}"',
            f'"{item.description}"',
            item.created_at,
            item.status
        ])

    # Write CSV with UTF-8-sig encoding
    with open("action_items.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print("Successfully exported action items to action_items.csv")

if __name__ == "__main__":
    main()