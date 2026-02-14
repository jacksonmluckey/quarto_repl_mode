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
    # Replace the entire cell Div with a single REPL-formatted code block
    return pf.CodeBlock(result, classes=["pycon"])


def main(doc=None):
    return pf.run_filter(handle_cell, doc=doc)


if __name__ == "__main__":
    main()
