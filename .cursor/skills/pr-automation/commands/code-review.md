# Code Review

Review the code for correctness, security, quality, and test coverage.

## Review Checklist

1. **Correctness**: Does the code work as intended? Are there any logic errors?
2. **Security**: Check for injection vulnerabilities, authentication issues, exposed secrets, dependency vulnerabilities
3. **Code Quality**: Follows project conventions, proper error handling, clean code principles
4. **Testing**: Are there tests? Do they cover edge cases?

## Output Format

Categorize findings as:
- **Critical**: Must fix before merging (security issues, bugs, breaking changes)
- **Suggestion**: Should fix (code quality, best practices)
- **Nice to have**: Optional improvements (refactoring, documentation)

## Related Cursor Resources

### Rules
- `.cursor/rules/backend-architecture.mdc` - Backend architecture patterns
- `.cursor/rules/flutter-architecture.mdc` - Flutter architecture patterns
- `.cursor/rules/backend-testing.mdc` - Testing patterns
- `.cursor/rules/git-workflow.mdc` - Git workflow including code review

### Commands
- `/security-audit` - Security-focused review
- `/run-tests-and-fix` - Run tests before review
- `/lint-and-fix` - Lint code before review
