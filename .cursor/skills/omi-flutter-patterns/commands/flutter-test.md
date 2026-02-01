# Flutter Test

Run Flutter app tests.

## Purpose

Execute Flutter test suite and verify app functionality across platforms.

## Running Tests

### All Tests
```bash
cd app
flutter test
```

### Specific Test File
```bash
flutter test test/providers/capture_provider_test.dart
```

### With Coverage
```bash
flutter test --coverage
```

## Test Script

Use the test script:
```bash
cd app
./test.sh
```

## Test Structure

- **Unit tests**: `test/` - Test individual functions and widgets
- **Integration tests**: `test_driver/` - End-to-end tests

## Best Practices

- Run tests before committing
- Fix all test failures before merging
- Write tests for new features
- Test on all platforms when possible

## Related Documentation

- Testing: `.cursor/rules/testing.mdc`
- Flutter Architecture: `.cursor/rules/flutter-architecture.mdc`

## Related Cursor Resources

### Rules
- `.cursor/rules/testing.mdc` - General testing guidelines
- `.cursor/rules/flutter-architecture.mdc` - App structure

### Skills
- `.cursor/skills/omi-flutter-patterns/` - Flutter patterns including testing

### Subagents
- `.cursor/agents/flutter-developer/` - Can help with testing

### Commands
- `/run-tests-and-fix` - Run tests and fix failures
- `/flutter-setup` - Setup Flutter environment
