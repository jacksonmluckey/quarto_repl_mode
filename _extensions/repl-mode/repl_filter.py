"""Quarto Python filter that renders REPL-mode code chunks as interactive Python sessions."""

import code
import io
import sys

import panflute as pf
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import Python3Lexer, PythonConsoleLexer
from pygments.style import Style
from pygments.styles import get_style_by_name
from pygments.token import Generic

REPR_SENTINEL = "\x00REPR\x00"
CONTINUATION_KEYWORDS = frozenset({"else", "elif", "except", "finally", "case"})


def _has_unterminated_triple_quote(source):
    """Check if source has an odd number of triple-quote delimiters."""
    return (source.count('"""') % 2 == 1) or (source.count("'''") % 2 == 1)


def _make_repl_style(base_name):
    """Create a Pygments style based on base_name but with Generic.Output using the default text color."""
    base = get_style_by_name(base_name)
    default_color = base.style_for_token(Generic)["color"] or base.style_for_token(
        Generic.Output
    ).get("color", "")
    # Fall back to the base style's top-level text color
    if not default_color:
        default_color = base.style_for_token(Generic)["color"] or "f8f8f2"

    class REPLStyle(base):
        styles = dict(base.styles)
        styles[Generic.Output] = f"#{default_color}"

    return REPLStyle


class REPLSession:
    """Persistent REPL session that maintains state across chunks in a document."""

    def __init__(self):
        self.console = code.InteractiveConsole()

    def _flush_buffer(self, buffer, output_parts):
        """Compile and execute the accumulated buffer, appending results to output_parts."""
        full = "\n".join(buffer)

        try:
            # Try with trailing \n to signal end-of-block to compile_command
            compiled = code.compile_command(full + "\n", symbol="single")
        except SyntaxError:
            compiled = None
            # Show the lines and the syntax error
            output_parts.append(f">>> {buffer[0]}")
            for b in buffer[1:]:
                output_parts.append(f"... {b}")
            old_stderr = sys.stderr
            sys.stderr = captured_err = io.StringIO()
            self.console.showsyntaxerror()
            sys.stderr = old_stderr
            err = captured_err.getvalue()
            if err:
                output_parts.append(err.rstrip())
            return

        if compiled is None:
            # Still incomplete even with trailing newline — shouldn't happen in flush,
            # but handle gracefully by just showing the lines
            output_parts.append(f">>> {buffer[0]}")
            for b in buffer[1:]:
                output_parts.append(f"... {b}")
            return

        output_parts.append(f">>> {buffer[0]}")
        for b in buffer[1:]:
            output_parts.append(f"... {b}")

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_displayhook = sys.displayhook
        sys.stdout = captured_out = io.StringIO()
        sys.stderr = captured_err = io.StringIO()

        repr_values = []

        def _capture_displayhook(value):
            if value is not None:
                repr_values.append(repr(value))
                builtins = self.console.locals.setdefault("__builtins__", {})
                if isinstance(builtins, dict):
                    builtins["_"] = value
                else:
                    setattr(builtins, "_", value)

        sys.displayhook = _capture_displayhook
        self.console.runcode(compiled)

        stdout_val = captured_out.getvalue()
        stderr_val = captured_err.getvalue()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        sys.displayhook = old_displayhook

        if stdout_val:
            output_parts.append(stdout_val.rstrip())
        if stderr_val:
            output_parts.append(stderr_val.rstrip())
        for rv in repr_values:
            output_parts.append(REPR_SENTINEL + rv)

    @staticmethod
    def _next_line_is_continuation(lines, i):
        """Check if the line after index i starts with a continuation keyword."""
        if i + 1 >= len(lines):
            return False
        next_stripped = lines[i + 1].lstrip()
        if not next_stripped:
            return False
        next_keyword = next_stripped.split()[0].rstrip(":")
        return next_keyword in CONTINUATION_KEYWORDS

    @staticmethod
    def _is_continuation_keyword(line):
        """Check if a line starts with a continuation keyword."""
        stripped = line.lstrip()
        if not stripped:
            return False
        keyword = stripped.split()[0].rstrip(":")
        return keyword in CONTINUATION_KEYWORDS

    def execute(self, source: str) -> str:
        """Execute source code line-by-line and return REPL-formatted output."""
        lines = source.strip().split("\n")
        output_parts = []
        buffer = []

        for i, line in enumerate(lines):
            # If buffer has an incomplete block and the new line is unindented
            # (starts a new statement), flush the buffer first.
            # Skip this check for continuation keywords (else, elif, except, etc.)
            if buffer and not line.startswith((" ", "\t")) and line.strip():
                if not self._is_continuation_keyword(line):
                    full = "\n".join(buffer)
                    try:
                        compiled = code.compile_command(full, symbol="single")
                    except SyntaxError:
                        compiled = "error"
                    if compiled is None and not _has_unterminated_triple_quote(full):
                        # Buffer is incomplete — flush it before starting the new line
                        self._flush_buffer(buffer, output_parts)
                        buffer = []

            buffer.append(line)
            full = "\n".join(buffer)

            try:
                compiled = code.compile_command(full, symbol="single")
            except SyntaxError:
                # Check if this might be an unterminated triple-quoted string
                if _has_unterminated_triple_quote(full):
                    continue
                # Syntax error — flush buffer with error
                self._flush_buffer(buffer, output_parts)
                buffer = []
                continue

            if compiled is None:
                # Incomplete statement — accumulate more lines
                continue

            # Complete statement — but don't flush if next line is a continuation
            if self._next_line_is_continuation(lines, i):
                continue

            self._flush_buffer(buffer, output_parts)
            buffer = []

        # Flush any remaining buffer (e.g., trailing block statement)
        if buffer:
            self._flush_buffer(buffer, output_parts)

        return "\n".join(output_parts)


session = REPLSession()


def handle_cell(elem, doc):
    if not isinstance(elem, pf.Div):
        return None

    if "cell" not in elem.classes:
        return None

    if elem.attributes.get("repl-mode") != "true":
        return None

    # Find the source CodeBlock inside this cell Div
    source = None
    for child in elem.content:
        if isinstance(child, pf.Div) and "cell-code" in child.classes:
            for subchild in child.content:
                if isinstance(subchild, pf.CodeBlock):
                    source = subchild.text
                    break
        elif isinstance(child, pf.CodeBlock) and "cell-code" in child.classes:
            source = child.text
        if source is not None:
            break

    if source is None:
        return None

    result = session.execute(source)
    # Use Pygments to syntax-highlight the REPL output with inline styles.
    # Set via `repl-highlight-style: monokai` in document or _quarto.yml metadata.
    pygments_style = "default"
    if doc:
        hl = doc.get_metadata("repl-highlight-style", None)
        if hl and isinstance(hl, str):
            pygments_style = hl
    repl_style = _make_repl_style(pygments_style)
    formatter = HtmlFormatter(nowrap=True, noclasses=True, style=repl_style)
    py_formatter = HtmlFormatter(nowrap=True, noclasses=True, style=pygments_style)
    py_lexer = Python3Lexer()

    # Highlight contiguous console lines (>>> and ...) as a block so
    # PythonConsoleLexer can properly parse continuation lines.
    # Repr output lines get individual Python syntax highlighting.
    console_lexer = PythonConsoleLexer()
    lines = result.split("\n")
    highlighted_parts = []
    console_buf = []

    def flush_console():
        if console_buf:
            block = "\n".join(console_buf)
            highlighted_parts.append(
                highlight(block, console_lexer, formatter).rstrip("\n")
            )
            console_buf.clear()

    for line in lines:
        if line.startswith(REPR_SENTINEL):
            flush_console()
            repr_text = line[len(REPR_SENTINEL) :]
            highlighted_parts.append(
                highlight(repr_text, py_lexer, py_formatter).rstrip("\n")
            )
        else:
            console_buf.append(line)

    flush_console()
    highlighted = "\n".join(highlighted_parts)
    html = f'<div class="sourceCode"><pre class="sourceCode pycon"><code class="sourceCode pycon">{highlighted}</code></pre></div>'
    return pf.RawBlock(html, format="html")


def main(doc=None):
    return pf.run_filter(handle_cell, doc=doc)


if __name__ == "__main__":
    main()
