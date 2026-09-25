# Import Omi action items into Trello boards

Use this recipe to convert Omi action items into standard Trello board JSON exports. You can import the resulting file directly into Trello to populate Kanban lists ("To Do" and "Completed") with due dates, completion states, and conversation notes.

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation

## Usage

Export and generate a Trello board JSON file:

```sh
omi --json action-item list --limit 100 | python action_items_to_trello.py - --board-name "Omi Tasks" -o trello_board.json
```

Or convert a saved action items export file:

```sh
python action_items_to_trello.py action_items.json --board-name "Sprint Backlog" -o trello_board.json
```

Output:
```
Wrote Trello board 'Sprint Backlog' with 24 cards to trello_board.json
```

## How to Import into Trello

1. Open [Trello](https://trello.com) and navigate to your workspace.
2. Select **Create board** or open an existing board.
3. Use Trello's JSON import feature or power-up to load `trello_board.json`.
4. Open tasks appear under the **To Do** list; completed items are pre-placed in **Completed** with checked completion status.

## Features

- **Standard Trello Schema**: Emits standard board structure with `lists` and `cards`.
- **Status Separation**: Automatically routes open tasks to "To Do" and resolved tasks to "Completed".
- **Due Date Support**: Retains ISO 8601 timestamps for Trello due date reminders.
- **Pure Standard Library**: Zero external dependencies required.
