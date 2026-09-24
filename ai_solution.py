```sql
-- goals_sqlite_schema.sql
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    status TEXT,
    goal_type TEXT,
    progress_percentage REAL DEFAULT (0.0)
);
CREATE INDEX IF NOT EXISTS idx_status ON goals (status);
CREATE INDEX IF NOT EXISTS idx_goal_type ON goals (goal_type);
CREATE INDEX IF NOT EXISTS idx_created_at ON goals (created_at);
```

```python
# goals_to_sqlite.py
import sqlite3

def goals_to_sqlite(filepath="goals.db"):
    with sqlite3.connect(filepath) as conn:
        conn.execute("PRAGMA journal_mode=WAL;");
        # Create table if not exists
        conn.execute('''CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            status TEXT,
            goal_type TEXT,
            progress_percentage REAL DEFAULT (0.0)
        );''')
        # Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON goals (status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_goal_type ON goals (goal_type);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON goals (created_at);")
        
if __name__ == "__main__":
    # Example usage
    goals_to_sqlite()
```

```python
# test_goals_to_sqlite.py
from goals_to_sqlite import goals_to_sqlite

def test_goals_to_sqlite():
    import sqlite3
    filepath = "goals.db"
    goals_to_sqlite(filepath)
    conn = sqlite3.connect(filepath)
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE name='goals';")
    schema = cursor.fetchone()
    assert "created_at" in schema[0], "Schema should include created_at column"
    conn.close()

    # Test that the function runs without error
    goals_to_sqlite()
```

```markdown
# goals_sqlite.md

To use the goals SQLite database recipe:

1. Create or connect to the database:
```python
goals_to_sqlite(filepath="goals.db")
```

2. Query goals with various filters:
```python
import sqlite3
conn = sqlite3.connect("goals.db")
for row in conn.execute("SELECT goal, created_at, status, progress_percentage FROM goals;"):
    print(row)
conn.close()
```

3. The table includes:
- `id` (primary key, auto-increment)
- `goal` (text, not null)
- `created_at` (UTC timestamp)
- `status` (text)
- `goal_type` (text)
- `progress_percentage` (real, default 0.0)

4. The schema includes indexes on `status`, `goal_type`, and `created_at` for efficient querying.
```