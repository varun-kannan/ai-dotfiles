# Python rules

- Use the project's environment tool. Do not install into the global interpreter.
- Confirm a new package exists with `python3 -m pip index versions <name>` before importing it.
- Annotate public function signatures. Run the configured type checker if the project has one.
- No bare `except:`. Catch the narrowest exception and re-raise with `from`.
- Use `pathlib` and pass `encoding="utf-8"` when opening text files.
- Subprocesses take a list and `shell=False`.
- No mutable default arguments.
- Use `logging.getLogger(__name__)`; do not configure the root logger in library code.
