# epaper-colorcal

Drive a CHNSpec CR30 spectral colorimeter to produce measured e-paper color palettes

[![PyPI](https://img.shields.io/pypi/v/epaper-colorcal?style=flat-square)](https://pypi.org/project/epaper-colorcal/)
[![Python](https://img.shields.io/pypi/pyversions/epaper-colorcal?style=flat-square)](https://pypi.org/project/epaper-colorcal/)
[![License](https://img.shields.io/github/license/OpenDisplay/epaper-colorcal?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/OpenDisplay/epaper-colorcal/test.yml?style=flat-square&label=tests)](https://github.com/OpenDisplay/epaper-colorcal/actions/workflows/test.yml)
[![Lint](https://img.shields.io/github/actions/workflow/status/OpenDisplay/epaper-colorcal/lint.yml?style=flat-square&label=lint)](https://github.com/OpenDisplay/epaper-colorcal/actions/workflows/lint.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-strict-blue?style=flat-square)](https://mypy.readthedocs.io/)

## Installation

```bash
pip install epaper-colorcal
```

## Quick Start

```python
# TODO: Add a simple usage example
import epaper_colorcal

# Example usage here
```

## Features

<!-- TODO: List key features -->
- Feature 1
- Feature 2
- Feature 3

## Usage

### Basic Example

```python
# TODO: Add detailed usage examples
```

### Advanced Usage

<!-- TODO: Document advanced features -->

## API Reference

<!-- TODO: Document main classes, functions, and parameters -->

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/OpenDisplay/epaper-colorcal.git
cd epaper-colorcal

# Install with all dependencies
uv sync --all-extras
```

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=src/epaper_colorcal

# Run specific test file
uv run pytest tests/test_specific.py -v
```

### Code Quality

```bash
# Lint code
uv run ruff check .

# Format code (if ruff format is configured)
uv run ruff format .

# Type check
uv run mypy src/epaper_colorcal
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit using conventional commits (`feat:`, `fix:`, etc.)
6. Push to your fork
7. Open a Pull Request
