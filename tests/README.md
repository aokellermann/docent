## Database for Integration Tests

Integration tests require a test Postgres database. If you have Postgres set up for local Docent development, you shouldn't need to do anything extra. The test fixture will create a new database called `_pytest_docent_test` and wipe it at the end of the test session.

## Test Execution

### Run All Tests
```bash
# Run complete test suite
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=docent_core.services --cov-report=html
```

### Run by Test Type
```bash
# Unit tests only (fast)
python -m pytest -m unit -v

# Integration tests only (slower)
python -m pytest -m integration -v

# Exclude slow tests
python -m pytest -m "not slow" -v
```
