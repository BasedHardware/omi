# Security Audit

Perform a security-focused review of the code.

## Focus Areas

1. **Injection vulnerabilities**: SQL, NoSQL, command, LDAP, XPath, etc.
2. **Authentication & Authorization**: Proper auth checks, session management, privilege escalation
3. **Secrets management**: No hardcoded secrets, proper use of environment variables
4. **Dependencies**: Check for known vulnerabilities in dependencies
5. **Input validation**: Sanitization, validation, encoding
6. **Error handling**: No information leakage in error messages
7. **Cryptography**: Proper use of encryption, hashing, secure random

## Output

List all security findings with severity (Critical, High, Medium, Low) and remediation steps.

## Related Cursor Resources

### Rules
- `.cursor/rules/backend-architecture.mdc` - Backend architecture patterns
- `.cursor/rules/backend-api-patterns.mdc` - API security patterns
- `.cursor/rules/plugin-development.mdc` - Plugin security patterns

### Commands
- `/code-review` - General code review
- `/lint-and-fix` - Fix linting issues
