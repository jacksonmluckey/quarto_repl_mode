# quarto-repl-mode

A Quarto filter that renders Python code chunks as interactive REPL sessions with `>>>` prompts, inline output, and syntax highlighting.

## Usage

Add `#| repl-mode: true` to any Python chunk:

````qmd
```{python}
#| repl-mode: true
x = 42
x
x * 2
```
````

Renders as:

```pycon
>>> x = 42
>>> x
42
>>> x * 2
84
```

Chunks without `#| repl-mode: true` render normally. State is shared across all chunks in a document.

## Setup

Register the filter in `_quarto.yml`:

```yaml
filters:
  - repl_filter.py
```

Optionally set the Pygments highlight style for REPL output (defaults to `default`):

```yaml
repl-highlight-style: monokai
```

It will not automatically sync with the Quarto syntax highlighting theme.

Install dependencies:

```bash
uv sync
```

## Features

- Expression results (`repr`) are syntax-highlighted; `print()` output is plain text
- Compound statements work: `if/elif/else`, `try/except/finally`, `for/else`, multiline strings
- State persists across chunks (variables, imports, function definitions)
- Errors display inline without breaking the session

## Tests

```bash
uv run pytest test_repl_filter.py -v
```
