# Backend Test

Run backend tests with proper environment setup.

## Purpose

Execute backend test suite and verify code changes work correctly.

## Running Tests

### All Tests
```bash
cd backend
python -m pytest tests/ -v
```

### Specific Test File
```bash
python -m pytest tests/unit/test_speaker_sample.py -v
```

### With Coverage
```bash
python -m pytest tests/ --cov=. --cov-report=html
```

### Integration Tests Only
```bash
python -m pytest tests/integration/ -v
```

## Test Script

Use the test script:
```bash
cd backend
./test.sh
```

## Test Structure

- **Unit tests**: `tests/unit/` - Fast, mock external dependencies
- **Integration tests**: `tests/integration/` - Test component interactions

## Best Practices

- Run tests before committing
- Fix all test failures before merging
- Maintain high test coverage
- Write tests for new features

## Related Documentation

- Backend Testing: `.cursor/rules/backend-testing.mdc`
- Testing: `.cursor/rules/testing.mdc`
