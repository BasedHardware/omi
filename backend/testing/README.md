# Memory Testing Tools

This directory contains scripts for testing the memory system functionalities, including creating mock memories and managing them.

## Available Tools

1. `create_mock_memories.py` - Create mock memories for testing purposes
2. `memory_test_tools.py` - Manage existing memories (list, review, edit, delete)

## Prerequisites

- Python 3.x
- Backend environment properly set up with dependencies installed
- Access to the database (Firebase/Firestore)
- A valid user ID (UID)

## Getting Your User ID

There are several ways to get your user ID:

### From the Running App
1. Open your browser's developer console (F12)
2. In the console, execute:
   ```javascript
   // If using Firebase auth
   firebase.auth().currentUser.uid
   ```
   Or check localStorage for auth data.

### From the Flutter App
1. Open the Flutter app
2. Look for your profile settings which may display your UID
3. Enable developer mode if available to view more technical information

## How to Use the Scripts

### Setting Up

1. Navigate to the backend directory and activate the virtual environment:
   ```bash
   cd /Users/pk/repo/_OMI/omi_monorepo/backend
   source venv/bin/activate
   ```

### Creating Mock Memories

```bash
python testing/create_mock_memories.py --uid YOUR_USER_ID --count 5
```

Options:
- `--uid` (required): Your user ID
- `--count` (optional): Number of memories to create (default: 5, max: 10)
- `--manual` (optional flag): Mark memories as manually added (they will be automatically approved)

### Managing Memories

The `memory_test_tools.py` script provides several commands:

#### Listing Memories
```bash
python testing/memory_test_tools.py list --uid YOUR_USER_ID
```

Options:
- `--limit` (optional): Number of memories to list (default: 10)
- `--offset` (optional): Offset for pagination (default: 0)

#### Reviewing a Memory
```bash
# To approve:
python testing/memory_test_tools.py review --uid YOUR_USER_ID --memory-id MEMORY_ID --approve

# To reject:
python testing/memory_test_tools.py review --uid YOUR_USER_ID --memory-id MEMORY_ID --reject
```

#### Editing a Memory
```bash
python testing/memory_test_tools.py edit --uid YOUR_USER_ID --memory-id MEMORY_ID --content "New memory content"
```

#### Changing Memory Visibility
```bash
python testing/memory_test_tools.py visibility --uid YOUR_USER_ID --memory-id MEMORY_ID --visibility public
# OR
python testing/memory_test_tools.py visibility --uid YOUR_USER_ID --memory-id MEMORY_ID --visibility private
```

#### Deleting a Memory
```bash
python testing/memory_test_tools.py delete --uid YOUR_USER_ID --memory-id MEMORY_ID
```

## Complete Testing Workflow Example

1. Create test memories:
   ```bash
   python testing/create_mock_memories.py --uid user123 --count 5
   ```

2. List created memories:
   ```bash
   python testing/memory_test_tools.py list --uid user123
   ```

3. Review a memory (substitute the actual memory ID):
   ```bash
   python testing/memory_test_tools.py review --uid user123 --memory-id abc123 --approve
   ```

4. Edit a memory:
   ```bash
   python testing/memory_test_tools.py edit --uid user123 --memory-id abc123 --content "My updated memory content"
   ```

5. Change visibility:
   ```bash
   python testing/memory_test_tools.py visibility --uid user123 --memory-id abc123 --visibility private
   ```

6. Delete a memory:
   ```bash
   python testing/memory_test_tools.py delete --uid user123 --memory-id abc123
   ```

## Authentication Notes

The scripts use the backend's existing authentication system. No additional keys are needed because:

1. The scripts directly access the database using the backend's database client
2. They operate on the database using your user ID
3. Server-side authentication is handled through the backend configuration

If you encounter permission errors, verify that your backend environment has the proper Firebase credentials set up.