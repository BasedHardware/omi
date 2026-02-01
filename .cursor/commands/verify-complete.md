# Verify Work is Complete

Verify that completed work actually functions as claimed.

## Purpose

Skeptically verify that work marked as complete actually works. Runs end-to-end tests, verifies implementations exist and function, checks edge cases, and reports what's incomplete.

## When to Use

Use this command when:
- After tasks are marked as complete
- When user says "done" or "complete"
- Before marking work as finished
- When verifying implementations
- After feature implementation

## Process

1. **Identify What Was Claimed**: Review task description or conversation to understand what was supposed to be completed
2. **Verify Implementation Exists**: Check that implementations actually exist
   - Files were created/modified
   - Functions/classes exist
   - Code is present (not just stubs)
   - No TODO/FIXME comments indicating incomplete work
3. **Test Functionality**: Run tests to verify it works
   - Run unit tests for new code
   - Run integration tests if applicable
   - Test the feature manually if possible
   - Verify edge cases are handled
   - Check error cases work correctly
4. **Check Edge Cases**: Verify edge cases are handled
   - Test with invalid inputs
   - Test boundary conditions
   - Test error scenarios
   - Test with different states
   - Test integration points
5. **Report Findings**: Provide comprehensive verification report
   - What was verified and passed
   - What was claimed but incomplete or broken
   - Specific issues that need to be addressed
   - Missing functionality
   - Test failures

## Verification Checklist

- [ ] Implementation exists (not just stubs)
- [ ] Code compiles/runs without errors
- [ ] Unit tests pass
- [ ] Integration tests pass (if applicable)
- [ ] Manual testing confirms functionality
- [ ] Edge cases are handled
- [ ] Error cases are handled
- [ ] Documentation is updated
- [ ] No obvious bugs

## Report Format

### Verified and Passed
List what was verified and works correctly

### Claimed but Incomplete
List what was claimed but not fully implemented
- Specific gaps or missing pieces

### Broken or Not Working
List what doesn't work
- Specific errors or failures
- Test failures with details

### Issues to Address
Specific issues that need fixing
- Priority level for each issue

## Be Thorough and Skeptical

- Don't accept claims at face value
- Test everything yourself
- Look for edge cases
- Verify end-to-end functionality
- Check that tests actually test the right thing
- Don't just check that test files exist - verify they pass

## Related Cursor Resources

### Subagents
- `.cursor/agents/verifier.md` - Verification subagent
- `.cursor/agents/test-runner.md` - For running tests

### Rules
- `.cursor/rules/verification.mdc` - Verification guidelines
- `.cursor/rules/common-mistakes.mdc` - Common mistakes to check for
- `.cursor/rules/testing.mdc` - Testing requirements

### Commands
- `/run-tests-and-fix` - Run tests to verify
