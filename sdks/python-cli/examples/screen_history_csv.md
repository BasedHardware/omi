# Screen History → CSV Recipe

This recipe converts a screen history file (JSON) into a CSV that can be safely
imported into any spreadsheet application.  The CSV contains three columns:

| Column     | Description                                      |
|------------|--------------------------------------------------|
| `timestamp`| The timestamp of the screen capture (ISO‑8601 or any string). |
| `text`     | The raw text captured from the screen.           |
| `ocr_text` | OCR‑extracted text (may be empty).               |

## Prerequisites

* Python 3.8+ installed.
* The input file must be a JSON array of objects, each containing at least
  `timestamp` and `text`.  `ocr_text` is optional.

## Usage

