# quarto-repl-mode

A Quarto filter that renders Python code chunks as an interactive REPL session.

An [example Quarto document](examples/example.qmd) is rendered [here](examples/example.html).

New lines begin with `>>>` prompts and `...` multi-line continuations.

Expression results are rendered as inline output immeditately following the line they come from. The inline output is syntax highlighted. `print()` output is plain text.

Compound statements work like `if/elif/else`, `try/except/finally`, `for/else`, and multiline strings are supported.

State (variables, imports, function definitions) is shared across all chunks in a document like normal Quarto documents.

Chunks without `#| repl-mode: true` render normally.

Errors display inline without breaking the session if `#| eval: False` is included to prevent the error from ending the Quarto render execution.

The extension code is in [`_extensions/repl-mode/repl_filter.py`](_extensions/repl-mode/repl_filter.py).

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

## Installation

Install the Quarto extension:

```bash
quarto add jacksonmluckey/quarto_repl_mode
```

Install Python dependencies:

```bash
uv add panflute pygments
```

## Setup

Add the filter in your `_quarto.yml`:

```yaml
filters:
  - repl-mode
```

Optionally set the Pygments highlight style for REPL output (defaults to `default`):

```yaml
repl-highlight-style: monokai
```

It will not automatically sync with the Quarto syntax highlighting theme.

## Styling

REPL-mode chunks use the `pycon` language class, while normal Python chunks use `python`. You can target them separately in CSS:

```css
pre.sourceCode.pycon { /* REPL mode */ }
pre.sourceCode.python { /* normal code */ }
```

## Tests

The tests are in [`tests/test_repl_filter.py`](tests/test_repl_filter.py).

```bash
uv run pytest tests/test_repl_filter.py -v
```
