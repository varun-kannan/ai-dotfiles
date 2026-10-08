---
name: python-patterns
description: Idiomatic Python covering project layout and tooling, type hints, dataclasses, context managers, exception handling, subprocess safety, pathlib, and common pitfalls. Use when writing or reviewing Python code or pyproject configuration.
---

# Python Patterns

Check `pyproject.toml` for the supported Python version and tools (ruff, mypy, pytest) before choosing syntax.

## Environment
- Use the project's existing environment tool (uv, poetry, pip with a lockfile). Do not install globally.
- Confirm a package exists before adding it: `python3 -m pip index versions <name>`.

## Types
- Annotate public function signatures. Use built-in generics (`list[str]`, `dict[str, int]`) on Python 3.9+.
- `Optional[X]` is `X | None` on 3.10+. Use the form the project's version supports.
- Run `mypy` or `pyright` if the project has it configured. Do not add it if it does not.

## Data
- Use `@dataclass(frozen=True)` for value objects. Use `slots=True` on 3.10+ for many small instances.
- Mutable default arguments are shared between calls. Use `None` and create inside the function.

```python
def add_item(item: str, items: list[str] | None = None) -> list[str]:
    items = [] if items is None else items
    items.append(item)
    return items
```

## Files and paths
- Use `pathlib.Path`. Open with `with` and pass `encoding="utf-8"` explicitly.
- To confine user-supplied paths: `resolved = (root / name).resolve()` then `resolved.is_relative_to(root.resolve())` (3.9+).

## Exceptions
- Catch the narrowest exception. Never a bare `except:`; it catches `KeyboardInterrupt`.
- Re-raise with context: `raise ConfigError("bad port") from exc`.
- Use `contextlib.suppress(KeyError)` only for a single expected failure.

## Subprocesses
- Pass a list and leave `shell=False`. Never build a command string from user input.

```python
subprocess.run(["git", "log", "-n", str(count)], check=True, capture_output=True, text=True)
```

## Iteration
- Use `enumerate`, `zip(strict=True)` (3.10+) for equal-length checks, and generators for large streams.
- Do not modify a list while iterating over it.

## Common traps
- `is` compares identity. Use `==` for values; `is None` for None.
- Late-binding closures in loops: bind with a default argument or `functools.partial`.
- Integer division: `//` for floor, `/` always returns float.

## Logging
- Use `logging.getLogger(__name__)`. Do not configure the root logger inside a library.
- Log structured values with `%s` placeholders, not f-strings, so disabled levels cost nothing.
