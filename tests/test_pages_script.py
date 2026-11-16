import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).parent.parent / "app" / "static"
PAGES = ["review.html", "upload.html"]


def _script(name: str) -> str:
    html = (STATIC / name).read_text(encoding="utf-8")
    match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert match, f"{name} has no script"
    return match.group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("name", PAGES)
def test_page_script_has_valid_syntax(name: str, tmp_path: Path) -> None:
    file = tmp_path / "page.js"
    file.write_text(_script(name), encoding="utf-8")

    result = subprocess.run(
        ["node", "--check", str(file)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", PAGES)
def test_api_key_box_is_wired_once(name: str) -> None:
    assert _script(name).count('getElementById("apikey")') == 1
