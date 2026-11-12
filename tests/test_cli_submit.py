from pathlib import Path
from types import SimpleNamespace

import httpx

from app import cli

FIXTURES = Path(__file__).parent / "fixtures"


def _args():
    return [
        "analyze",
        "--invoice",
        str(FIXTURES / "invoice.json"),
        "--po",
        str(FIXTURES / "po.json"),
        "--contract",
        str(FIXTURES / "contract.json"),
        "--submit",
    ]


def test_submit_posts_the_case_to_the_review_server(monkeypatch, capsys):
    sent = {}

    def fake_post(url, json, timeout):
        sent["url"] = url
        sent["json"] = json
        return SimpleNamespace(status_code=201)

    monkeypatch.setattr(cli.httpx, "post", fake_post)

    code = cli.main(_args())

    assert code == 0
    assert sent["url"].endswith("/cases")
    assert sent["json"]["case_id"] == "INV-2041-01"
    assert sent["json"]["finding"] == "UNAGREED-FEE"
    assert sent["json"]["requires_human_approval"] is True
    assert "submitted for review" in capsys.readouterr().err


def test_submit_reports_an_existing_case(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.httpx, "post", lambda url, json, timeout: SimpleNamespace(status_code=409)
    )

    assert cli.main(_args()) == 0
    assert "already in the review queue" in capsys.readouterr().err


def test_submit_fails_cleanly_when_the_server_is_down(monkeypatch, capsys):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(cli.httpx, "post", fake_post)

    assert cli.main(_args()) == 3
    assert "cannot reach" in capsys.readouterr().err
