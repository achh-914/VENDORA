import json
from pathlib import Path

from app.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _args(*extra):
    return [
        "analyze",
        "--invoice",
        str(FIXTURES / "invoice.json"),
        "--po",
        str(FIXTURES / "po.json"),
        "--contract",
        str(FIXTURES / "contract.json"),
        *extra,
    ]


def test_analyze_prints_the_case_file(capsys):
    code = main(_args())
    out = capsys.readouterr().out

    assert code == 0
    assert "UNAGREED-FEE" in out
    assert "3,000.00" in out
    assert "MSA-ACME-2025" in out
    assert "HOLD_INVOICE" in out
    assert "human approval" in out


def test_analyze_json_output_is_a_valid_case_file(capsys):
    code = main(_args("--json"))
    cases = json.loads(capsys.readouterr().out)

    assert code == 0
    assert cases[0]["finding"] == "UNAGREED-FEE"
    assert cases[0]["delta"] == 3000.0
    assert cases[0]["requires_human_approval"] is True


def test_missing_file_returns_an_error(capsys):
    code = main(["analyze", "--invoice", "nope.json", "--po", "x", "--contract", "y"])

    assert code == 2
    assert "file not found" in capsys.readouterr().err
