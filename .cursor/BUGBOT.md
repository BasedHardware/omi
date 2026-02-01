# Bugbot Review Rules

This file contains review guidelines for Bugbot to automatically catch issues before they reach human reviewers. These rules complement GitHub Actions automation (linting, tests) and focus on logic bugs, architectural issues, and patterns that automated tools miss.

> **Note**: See https://cursor.com/docs/cookbook/bugbot-rules for documentation.

## Security

### Secrets and Credentials
- Block exposed secrets, unsafe API calls, or missing authentication checks.
  - Check for hardcoded API keys (OPENAI_API_KEY, DEEPGRAM_API_KEY, PINECONE_API_KEY, REDIS_DB_PASSWORD, etc.)
  - Verify secrets are loaded from environment variables, not hardcoded
  - Check for secrets in commit history (if new files added)
  - Verify `.env` files are not committed (check `.gitignore`)

### Authentication & Authorization
- Verify all API endpoints have proper authentication (FastAPI Depends, Firebase Auth)
- Check for missing authorization checks (users accessing other users' data)
- Verify admin-only endpoints are properly protected
- Check for broken authentication flows (missing token validation)

### Input Validation
- Verify proper input validation and sanitization on all user inputs
- Check for SQL injection risks in database queries (even with ORMs)
- Verify XSS prevention in web frontend (proper escaping)
- Check for path traversal vulnerabilities in file operations
- Verify rate limiting on public endpoints

### Network Security
- Verify CORS configuration is appropriate (not too permissive)
- Check for missing HTTPS enforcement
- Verify WebSocket connections use secure protocols (WSS)
- Check for unsafe shell command execution (use subprocess safely)

## Backend Code Quality

### Import Hierarchy
- All imports must be at module top level (no in-function imports)
- Verify import hierarchy: `database/` → `utils/` → `routers/` → `main.py`
- Block imports from higher-level modules to lower-level modules
- Check for circular import dependencies
- Verify relative imports are used correctly

### FastAPI Patterns
- All endpoints must have proper error handling (HTTPException)
- Verify request/response validation using Pydantic models
- Check for proper authentication dependencies on protected routes
- Ensure async/await is used correctly for I/O operations
- Verify proper HTTP status codes (not always 200)
- Check for missing response models (type hints)
- Verify OpenAPI documentation is accurate

### Database Usage
- Firestore queries should use proper indexes (warn if query might be slow)
- Check for N+1 query problems
- Verify transactions are used for multi-step operations
- Pinecone operations should handle errors gracefully
- Redis operations should have timeout handling
- Check for memory leaks (large objects not freed after use)
- Verify connection pooling is used correctly
- Check for missing database connection error handling

### Error Handling
- All database operations should have try/except blocks
- LLM API calls should have retry logic and error handling
- WebSocket connections should handle disconnections gracefully
- Verify error messages don't leak sensitive information
- Check for swallowed exceptions (bare `except:` clauses)
- Verify proper logging of errors (not just print statements)

### Performance
- Check for blocking operations in async functions
- Verify expensive operations are cached appropriately
- Check for unnecessary database queries in loops
- Verify pagination is implemented for large result sets
- Check for memory-intensive operations without cleanup

## Flutter Code Quality

### Localization
- All user-facing strings must use `context.l10n.keyName` instead of hardcoded strings
- Block hardcoded English strings in UI components
- Verify ARB files are updated when new strings are added
- Check for missing translations (all locales should have keys)

### State Management
- Verify Provider patterns are used correctly
- Check for proper dispose() calls to prevent memory leaks
- Ensure ChangeNotifier.notifyListeners() is called appropriately
- Verify state is not mutated directly (use copyWith or new instances)
- Check for unnecessary rebuilds (missing const constructors)

### BLE Protocol
- Verify BLE operations handle connection failures
- Check for proper cleanup of BLE resources
- Ensure audio streaming handles interruptions correctly
- Verify BLE characteristic writes have proper error handling
- Check for race conditions in BLE state management

### Platform-Specific Code
- Platform-specific code (iOS/Android/macOS/Windows) should be properly isolated
- Verify platform checks are correct (not inverted)
- Check for missing platform implementations
- Verify platform-specific permissions are requested

## Web Frontend Code Quality

### TypeScript/JavaScript
- Verify TypeScript types are used correctly (no `any` types)
- Check for missing null/undefined checks
- Verify proper error boundaries in React components
- Check for memory leaks (event listeners not removed)
- Verify proper cleanup in useEffect hooks

### React/Next.js Patterns
- Verify proper use of Next.js App Router patterns
- Check for missing loading states
- Verify proper error handling in API routes
- Check for client-side only code in server components
- Verify proper hydration handling

### Performance
- Check for unnecessary re-renders
- Verify proper use of React.memo, useMemo, useCallback
- Check for large bundle sizes (unused imports)
- Verify proper image optimization
- Check for missing lazy loading

## Testing

### Test Coverage
- New features should include tests (unit tests for backend, widget tests for Flutter)
- Verify test coverage for critical paths (API endpoints, BLE communication, memory extraction)
- Check that tests are actually runnable and not skipped
- Verify tests cover edge cases and error conditions
- Check for flaky tests (tests that might fail intermittently)

### Test Quality
- Verify tests are independent (don't rely on execution order)
- Check for proper test isolation (mocking external dependencies)
- Verify tests have clear assertions (not just checking no exceptions)
- Check for missing test cleanup (database state, file system)

### Integration Tests
- Verify integration tests cover critical user flows
- Check for missing API integration tests
- Verify WebSocket integration tests exist
- Check for missing BLE integration tests

## Documentation

### Code Documentation
- API endpoints should have docstrings describing parameters and responses
- Complex functions should have inline comments explaining logic
- Verify README files are updated when setup steps change
- Check for missing type hints in Python functions
- Verify JSDoc comments in TypeScript functions

### API Documentation
- Verify API changes are reflected in OpenAPI/Swagger docs
- Check for missing endpoint documentation
- Verify request/response examples are accurate
- Check for breaking changes in API contracts

## Breaking Changes

### API Breaking Changes
- Detect breaking changes in API endpoints (removed parameters, changed response format)
- Verify versioning is used for breaking changes (v1, v2, etc.)
- Check for missing migration guides for breaking changes
- Verify deprecated endpoints have proper deprecation notices

### Database Breaking Changes
- Check for schema changes that break existing data
- Verify migrations are backwards compatible when possible
- Check for missing migration rollback scripts
- Verify data migration scripts are tested

### Configuration Breaking Changes
- Check for environment variable changes without documentation
- Verify configuration file format changes are documented
- Check for missing default values for new configuration options

## Performance & Scalability

### Backend Performance
- Check for slow database queries (missing indexes, full table scans)
- Verify proper use of caching (Redis, in-memory)
- Check for blocking operations in async code
- Verify proper connection pooling
- Check for memory leaks in long-running processes

### Frontend Performance
- Verify proper code splitting in Next.js
- Check for large bundle sizes
- Verify proper image optimization
- Check for unnecessary API calls
- Verify proper use of React performance optimizations

## Dependency Management

### Dependency Updates
- Check for security vulnerabilities in dependencies
- Verify dependency updates don't break existing code
- Check for missing dependency updates (outdated packages)
- Verify lock files are updated with dependency changes

### Dependency Conflicts
- Check for version conflicts in package managers
- Verify peer dependencies are satisfied
- Check for missing optional dependencies

## Git & Version Control

### Commit Quality
- Verify commit messages follow conventional commits format
- Check for large files committed (should use Git LFS)
- Verify .gitignore is updated for new file types
- Check for accidentally committed secrets

### Branch Management
- Verify feature branches are up to date with main
- Check for merge conflicts that need resolution
- Verify PR is targeting the correct base branch

## TODO/FIXME Comments

If any changed file contains `/(?:^|\s)(TODO|FIXME)(?:\s*:|\s+)/`, then:
- Add a non-blocking Bug titled "TODO/FIXME comment found"
- Body: "Replace TODO/FIXME with a tracked issue reference, e.g., `TODO(#1234): ...`, or remove it."
- If the TODO already references an issue pattern `/#\d+|[A-Z]+-\d+/`, mark the Bug as resolved automatically.

## Omi-Specific Patterns

### Backend
- Memory extraction should handle edge cases (empty transcripts, malformed data)
- Chat system should verify LangGraph state transitions are valid
- WebSocket endpoints should handle reconnection scenarios
- Verify conversation processing handles rate limits
- Check for proper cleanup of LLM API connections

### Flutter
- BLE device communication should handle device disconnection gracefully
- Audio streaming should verify codec compatibility
- Platform-specific code (iOS/Android/macOS/Windows) should be properly isolated
- Verify audio buffer management doesn't cause memory issues
- Check for proper handling of device permissions

### Firmware
- BLE service implementations should follow Zephyr patterns
- Audio codec operations should handle buffer overflows
- Check for proper resource cleanup in embedded code
- Verify interrupt handlers are properly implemented
- Check for stack overflow risks in recursive functions

## Integration with GitHub Actions

### Complementing Automated Checks
- GitHub Actions handles: ESLint, Prettier formatting, basic linting
- Bugbot focuses on: Logic bugs, architectural issues, security vulnerabilities, performance problems
- Verify changes that would break CI/CD (missing dependencies, configuration changes)
- Check for changes that require CI/CD updates (new test commands, new linting rules)

### Pre-Merge Checks
- Verify all GitHub Actions checks would pass (based on code changes)
- Check for missing test files when new features are added
- Verify linting would pass (catch issues before CI runs)
- Check for changes that require documentation updates
