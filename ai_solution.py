The code changes are as follows:

1. In `main.py`, the error handling was updated to replace the raw `str(e)` with a generic message.
2. A new test file `plugins/omi-notion-app/test_error_handling.py` was added with tests confirming the fix.
3. The tests are passing, and the changes ensure that internal details are not exposed.

The code solution is encapsulated in PR #15556, which addresses the error handling to prevent sensitive information from being exposed in the responses.