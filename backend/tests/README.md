# App Uninstallation Security Tests

## Dependencies

Before running the tests, ensure you have the necessary dependencies installed:

```bash
pip install pytest pytest-cov requests redis
```

## Test Files

`test_security.py` (in the `backend/tests` directory)

This test script verifies the key functionality:
- Simulates app installation and data storage in Redis
- Tests the uninstallation process to ensure all data is cleaned up
- Verifies no app-related data remains after uninstallation

## Running the Tests

There are two main ways to run the tests:

### 1. Using pytest (recommended for detailed testing)

```bash
# Activate your virtual environment (if using one)
source venv/bin/activate

# Run all tests
python -m pytest backend/tests

# Run a specific test
python -m pytest backend/tests/test_security.py
```

### 2. Using the standalone script (quick verification)

```bash
# Run directly from any directory
python backend/tests/test_security.py
```

This script provides a simple way to verify that the key functionality (pattern-based cleanup) is working correctly.
