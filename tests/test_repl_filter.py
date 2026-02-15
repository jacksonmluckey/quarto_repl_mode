"""Tests for repl_filter.py"""

import sys
from pathlib import Path

# Add the extension directory to sys.path so we can import the filter
sys.path.insert(0, str(Path(__file__).parent / "_extensions" / "repl-mode"))

from pygments.token import Generic

from repl_filter import REPR_SENTINEL, REPLSession, _make_repl_style


S = REPR_SENTINEL


class TestSimpleStatements:
    def setup_method(self):
        self.session = REPLSession()

    def test_assignment_no_output(self):
        result = self.session.execute("x = 42")
        assert result == ">>> x = 42"

    def test_expression_produces_repr(self):
        result = self.session.execute("x = 42\nx")
        assert result == f">>> x = 42\n>>> x\n{S}42"

    def test_arithmetic_expression(self):
        result = self.session.execute("2 + 3")
        assert result == f">>> 2 + 3\n{S}5"

    def test_multiple_expressions(self):
        result = self.session.execute("x = 10\nx\nx * 2")
        lines = result.split("\n")
        assert lines[0] == ">>> x = 10"
        assert lines[1] == ">>> x"
        assert lines[2] == f"{S}10"
        assert lines[3] == ">>> x * 2"
        assert lines[4] == f"{S}20"


class TestPrintVsRepr:
    def setup_method(self):
        self.session = REPLSession()

    def test_print_no_sentinel(self):
        result = self.session.execute('print("hello")')
        assert result == '>>> print("hello")\nhello'
        assert S not in result

    def test_string_expression_has_sentinel(self):
        result = self.session.execute("'hello'")
        assert result == f">>> 'hello'\n{S}'hello'"

    def test_print_and_repr_separated(self):
        """A function that prints and returns should show print first, repr second."""
        code = "def f():\n    print('side effect')\n    return 42\nf()"
        result = self.session.execute(code)
        lines = result.split("\n")
        # Find the output lines (after the f() call prompt)
        call_idx = next(i for i, line in enumerate(lines) if line == ">>> f()")
        output_lines = lines[call_idx + 1 :]
        assert "side effect" in output_lines
        assert f"{S}42" in output_lines
        # print output comes before repr
        print_idx = output_lines.index("side effect")
        repr_idx = output_lines.index(f"{S}42")
        assert print_idx < repr_idx


class TestMultiLineBlocks:
    def setup_method(self):
        self.session = REPLSession()

    def test_for_loop_with_print(self):
        result = self.session.execute("for i in range(3):\n    print(i)")
        lines = result.split("\n")
        assert lines[0] == ">>> for i in range(3):"
        assert lines[1] == "...     print(i)"
        assert "0" in lines
        assert "1" in lines
        assert "2" in lines
        # print output should not have sentinels
        for line in lines[2:]:
            assert not line.startswith(S)

    def test_for_loop_with_expression(self):
        result = self.session.execute("for i in range(3):\n    i")
        lines = result.split("\n")
        assert lines[0] == ">>> for i in range(3):"
        assert lines[1] == "...     i"
        # Expression results inside loops go through displayhook
        repr_lines = [line for line in lines if line.startswith(S)]
        assert len(repr_lines) == 3
        assert f"{S}0" in lines
        assert f"{S}1" in lines
        assert f"{S}2" in lines

    def test_if_block(self):
        result = self.session.execute("x = 5\nif x > 3:\n    print('big')")
        assert "big" in result
        assert S not in result  # print output, no repr

    def test_if_else(self):
        result = self.session.execute(
            "x = 5\nif x > 3:\n    print('big')\nelse:\n    print('small')"
        )
        lines = result.split("\n")
        output_lines = [line for line in lines if not line.startswith((">>>", "..."))]
        assert "big" in output_lines
        assert "small" not in output_lines
        assert not any("Error" in line for line in output_lines)

    def test_if_elif_else(self):
        result = self.session.execute(
            "x = 2\nif x > 3:\n    print('a')\nelif x > 1:\n    print('b')\nelse:\n    print('c')"
        )
        lines = result.split("\n")
        output_lines = [line for line in lines if not line.startswith((">>>", "..."))]
        assert "b" in output_lines
        assert not any("Error" in line for line in output_lines)

    def test_try_except(self):
        result = self.session.execute(
            "try:\n    1/0\nexcept ZeroDivisionError:\n    print('caught')"
        )
        assert "caught" in result
        assert "SyntaxError" not in result

    def test_try_except_finally(self):
        result = self.session.execute(
            "try:\n    x = 1\nexcept:\n    pass\nfinally:\n    print('done')"
        )
        assert "done" in result
        assert "SyntaxError" not in result

    def test_for_else(self):
        result = self.session.execute(
            "for i in []:\n    pass\nelse:\n    print('empty')"
        )
        assert "empty" in result
        assert "Error" not in result

    def test_while_else(self):
        result = self.session.execute(
            "x = 0\nwhile x < 0:\n    x += 1\nelse:\n    print('done')"
        )
        assert "done" in result
        assert "Error" not in result

    def test_multiple_except(self):
        result = self.session.execute(
            "try:\n    1/0\nexcept ValueError:\n    print('val')\nexcept ZeroDivisionError:\n    print('zero')"
        )
        lines = result.split("\n")
        output_lines = [line for line in lines if not line.startswith((">>>", "..."))]
        assert "zero" in output_lines
        assert "val" not in output_lines

    def test_multiline_string(self):
        result = self.session.execute('x = """hello\nworld"""\nx')
        repr_lines = [line for line in result.split("\n") if line.startswith(S)]
        assert len(repr_lines) == 1
        assert "hello" in repr_lines[0]
        assert "world" in repr_lines[0]

    def test_function_def_and_call(self):
        result = self.session.execute(
            "def greet(name):\n    return f'hi {name}'\ngreet('world')"
        )
        assert f"{S}'hi world'" in result


class TestStatePersistence:
    def setup_method(self):
        self.session = REPLSession()

    def test_variable_persists(self):
        self.session.execute("x = 99")
        result = self.session.execute("x")
        assert f"{S}99" in result

    def test_import_persists(self):
        self.session.execute("import math")
        result = self.session.execute("math.pi")
        assert S in result
        # Extract the repr value
        repr_line = [line for line in result.split("\n") if line.startswith(S)][0]
        value = float(repr_line[len(S) :])
        assert abs(value - 3.141592653589793) < 1e-10


class TestErrorHandling:
    def setup_method(self):
        self.session = REPLSession()

    def test_syntax_error(self):
        result = self.session.execute("def")
        assert "SyntaxError" in result

    def test_name_error(self):
        result = self.session.execute("undefined_var")
        assert "NameError" in result

    def test_error_does_not_break_session(self):
        self.session.execute("undefined_var")
        result = self.session.execute("x = 1\nx")
        assert f"{S}1" in result


class TestHighlighting:
    def test_make_repl_style_overrides_output_color(self):
        style = _make_repl_style("monokai")
        output_style = style.style_for_token(Generic.Output)
        # Should NOT be the default Monokai blue (#66d9ef)
        assert output_style["color"] != "66d9ef"
        # Should be the default text color
        assert output_style["color"] == "f8f8f2"

    def test_continuation_lines_are_highlighted(self):
        """Continuation lines (... prefix) should get syntax highlighting, not plain text."""
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import PythonConsoleLexer

        session = REPLSession()
        result = session.execute("if True:\n    x = 1\nelse:\n    x = 2")
        # Highlight as a block (the way handle_cell does it)
        console_lines = [line for line in result.split("\n") if not line.startswith(S)]
        block = "\n".join(console_lines)
        formatter = HtmlFormatter(nowrap=True, noclasses=True, style="monokai")
        html = highlight(block, PythonConsoleLexer(), formatter)
        # The "else" continuation line should have keyword highlighting,
        # not be a single default-color span
        for line in html.split("\n"):
            if "..." in line and "else" in line:
                assert line.count("<span") > 1, (
                    f"Continuation line lacks highlighting: {line}"
                )
                break
        else:
            raise AssertionError(
                "Could not find '... else' continuation line in output"
            )

    def test_make_repl_style_preserves_other_tokens(self):
        from pygments.styles import get_style_by_name

        base = get_style_by_name("monokai")
        custom = _make_repl_style("monokai")
        # Prompt style should be unchanged
        base_prompt = base.style_for_token(Generic.Prompt)
        custom_prompt = custom.style_for_token(Generic.Prompt)
        assert base_prompt["color"] == custom_prompt["color"]
        assert base_prompt["bold"] == custom_prompt["bold"]
