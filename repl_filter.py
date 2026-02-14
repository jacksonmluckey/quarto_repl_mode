#!/usr/bin/env python3
"""Quarto Python filter that renders REPL-mode code chunks as interactive Python sessions."""

import code
import io
import sys

import panflute as pf


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
        sys.stdout = captured_out = io.StringIO()
        sys.stderr = captured_err = io.StringIO()

        self.console.runcode(compiled)

        stdout_val = captured_out.getvalue()
        stderr_val = captured_err.getvalue()
        sys.stdout = old_stdout
        sys.stderr = old_stderr

        if stdout_val:
            output_parts.append(stdout_val.rstrip())
        if stderr_val:
            output_parts.append(stderr_val.rstrip())

    def execute(self, source: str) -> str:
        """Execute source code line-by-line and return REPL-formatted output."""
        lines = source.strip().split("\n")
        output_parts = []
        buffer = []

        for line in lines:
            # If buffer has an incomplete block and the new line is unindented
            # (starts a new statement), flush the buffer first
            if buffer and not line.startswith((" ", "\t")) and line.strip():
                full = "\n".join(buffer)
                try:
                    compiled = code.compile_command(full, symbol="single")
                except SyntaxError:
                    compiled = "error"
                if compiled is None:
                    # Buffer is incomplete — flush it before starting the new line
                    self._flush_buffer(buffer, output_parts)
                    buffer = []

            buffer.append(line)
            full = "\n".join(buffer)

            try:
                compiled = code.compile_command(full, symbol="single")
            except SyntaxError:
                # Syntax error — flush buffer with error
                self._flush_buffer(buffer, output_parts)
                buffer = []
                continue

            if compiled is None:
                # Incomplete statement — accumulate more lines
                continue

            # Complete statement — execute
            self._flush_buffer(buffer, output_parts)
            buffer = []

        # Flush any remaining buffer (e.g., trailing block statement)
        if buffer:
            self._flush_buffer(buffer, output_parts)

        return "\n".join(output_parts)


session = REPLSession()


def handle_code_block(elem, doc):
    if not isinstance(elem, pf.CodeBlock):
        return None

    # Detect repl-mode: Quarto puts #| directives on the parent Div's attributes
    is_repl = False
    if elem.parent and hasattr(elem.parent, 'attributes'):
        is_repl = elem.parent.attributes.get("repl-mode") == "true"

    if not is_repl:
        return None

    # Strip the #| repl-mode directive from the source if present
    source_lines = elem.text.split("\n")
    filtered = [
        line for line in source_lines
        if not line.strip().startswith("#| repl-mode") and not line.strip().startswith("#| REPL-mode")
    ]
    source = "\n".join(filtered)

    result = session.execute(source)
    return pf.CodeBlock(result, classes=["pycon"])


def main(doc=None):
    return pf.run_filter(handle_code_block, doc=doc)


if __name__ == "__main__":
    main()
