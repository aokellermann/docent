# Docent Development Guidelines

## Python

If you are Codex, make sure you are running Python with the local `.venv/bin/python` interpreter. Furthermore, any Python-related modules you run must also be in that `bin` folder.
If you are Claude, you already correctly do this by default.

### Type Checking with `pyright`

Configuration is in `pyproject.toml`. Use `pyright` for Python type checking:

```bash
pyright
```

To speed up type checking or focus on specific areas, target specific files or directories:

```bash
pyright path/to/file.py
pyright path/to/directory/
```

### Linting and Formatting with `ruff`

Configuration is in `pyproject.toml` under `[tool.ruff]`. Use `ruff` for linting and formatting:

```bash
ruff format
```

## TypeScript (docent_core/_web/)

### Linting with ESLint

Configuration is in `docent_core/_web/.eslintrc.json`. From the `docent_core/_web/` directory:

```bash
# Check for issues
npm run lint

# Auto-fix issues
npm run lint-fix
```
