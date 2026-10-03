```python
#!/usr/bin/env python
"""
Convert action items to CSV format.

Example:
    action_items_to_csv.py [-h] [--output OUTPUT]

Exports action items to a CSV file for spreadsheet or task tracker use.

"""

import argparse
import csv
import os

def action_items_to_csv(output="action_items.csv"):
    """
    Converts action items to CSV format and saves to file.

    Args:
        output (str, optional): Name of the output CSV file. Defaults to "action_items.csv".
    """
    action_items = [
        {"ID": "1", "Title": "Review the code", "Description": "Review the code for any issues."},
        {"ID": "2", "Title": "Update documentation", "Description": "Update the project documentation."},
        # Add more action items as needed
    ]

    with open(output, "w", newline="") as csvfile:
        fieldnames = ["ID", "Title", "Description"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in action_items:
            writer.writerow(item)
    print(f"Action items exported to {output}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert action items to CSV format.")
    parser.add_argument(
        "--output",
        type=str,
        nargs="?",
        default="action_items.csv",
        help="Name of the output CSV file.",
    )
    args = parser.parse_args()
    action_items_to_csv(args.output)
```