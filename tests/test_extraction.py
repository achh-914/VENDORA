from types import SimpleNamespace

import pytest

from app.agents.extraction import extract_document


class FakeMessages:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.kwargs = kwargs
        return SimpleNamespace(content=self.parent.blocks)


class FakeClient:
    def __init__(self, blocks):
        self.blocks = blocks
        self.kwargs = {}
        self.messages = FakeMessages(self)


def _tool_block(payload):
    return SimpleNamespace(type="tool_use", name="record_document", input=payload)


def test_extract_returns_structured_document(tmp_path):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    payload = {
        "doc_type": "invoice",
        "doc_id": "INV-2041",
        "total": 18000.0,
        "total_page": 1,
        "lines": [
            {
                "line_no": 4,
                "description": "Freight surcharge",
                "amount": 3000.0,
                "page": 1,
            }
        ],
    }
    client = FakeClient([_tool_block(payload)])

    doc = extract_document(pdf, client=client, provider="claude")

    assert doc.total == 18000.0
    assert doc.lines[0].description == "Freight surcharge"
    assert doc.lines[0].page == 1
    assert client.kwargs["tool_choice"]["name"] == "record_document"


def test_extract_raises_without_tool_output(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    client = FakeClient([SimpleNamespace(type="text", text="hello")])

    with pytest.raises(ValueError):
        extract_document(pdf, client=client, provider="claude")
