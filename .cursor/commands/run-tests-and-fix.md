# Run Tests and Fix

Run the appropriate test suite for the changed code, fix any failures, and re-run until all tests pass.

## Process

1. Identify which test suite to run based on changed files:
   - Backend changes: `backend/test.sh`
   - App changes: `app/test.sh`
   - Other: determine appropriate test command
2. Run the tests
3. If failures occur:
   - Analyze the failures
   - Fix the issues
   - Re-run tests
4. Repeat until all tests pass
5. Summarize what was fixed

## Related Cursor Resources

### Rules
- `.cursor/rules/testing.mdc` - General testing guidelines
- `.cursor/rules/backend-testing.mdc` - Backend testing patterns

### Commands
- `/backend-test` - Run backend tests
- `/flutter-test` - Run Flutter tests
- `/test-integration` - Run integration tests
