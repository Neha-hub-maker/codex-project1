from pathlib import Path

import pytest


@pytest.fixture
def fixture_diff():
    def read(name: str) -> str:
        return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")

    return read


@pytest.fixture
def new_python_diff():
    def make(source: str, path: str = "example.py") -> str:
        lines = source.split("\n")
        if lines[-1] == "":
            lines.pop()
        return (
            f"diff --git a/{path} b/{path}\n"
            f"new file mode 100644\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{line}\n" for line in lines)
        )

    return make
