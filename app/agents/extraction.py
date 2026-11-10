"""Extraction agent: reads a PDF with an LLM, returns fields with page refs.

Default provider is Gemini. Set VENDORA_PROVIDER=claude to use Claude instead.
"""

import base64
import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
TOOL_NAME = "record_document"

PROMPT = (
    "Extract this procurement document. Return every value exactly as written. "
    "'page' is the 1-based PDF page where the value appears. "
    "For invoices and purchase orders, extract every line item and the total. "
    "For contracts, extract every numbered clause about price, freight, "
    "delivery, fees, or payment terms. Never guess: use null if a value is missing."
)


class ExtractedLine(BaseModel):
    line_no: int
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float
    page: int = Field(ge=1)


class ExtractedClause(BaseModel):
    number: str
    text: str
    page: int = Field(ge=1)


class ExtractedDocument(BaseModel):
    doc_type: Literal["invoice", "purchase_order", "contract"]
    doc_id: str
    supplier: str | None = None
    buyer: str | None = None
    currency: str | None = None
    total: float | None = None
    total_page: int | None = None
    lines: list[ExtractedLine] = []
    clauses: list[ExtractedClause] = []


def _extract_claude(pdf_path, client=None, model=None) -> ExtractedDocument:
    import anthropic

    client = client or anthropic.Anthropic()
    model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    data = base64.standard_b64encode(Path(pdf_path).read_bytes()).decode()

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        tools=[
            {
                "name": TOOL_NAME,
                "description": "Record the structured contents of the document.",
                "input_schema": ExtractedDocument.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": data,
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            return ExtractedDocument.model_validate(block.input)
    raise ValueError("The model did not return structured data")


def _extract_gemini(pdf_path, client=None, model=None) -> ExtractedDocument:
    from google import genai
    from google.genai import types

    client = client or genai.Client()
    model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=Path(pdf_path).read_bytes(), mime_type="application/pdf"),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedDocument,
        ),
    )

    if response.parsed is None:
        raise ValueError("The model did not return structured data")
    if isinstance(response.parsed, ExtractedDocument):
        return response.parsed
    return ExtractedDocument.model_validate(response.parsed)


def extract_document(pdf_path, client=None, model=None, provider=None) -> ExtractedDocument:
    provider = provider or os.getenv("VENDORA_PROVIDER", "gemini")
    if provider == "claude":
        return _extract_claude(pdf_path, client, model)
    return _extract_gemini(pdf_path, client, model)


if __name__ == "__main__":
    print(extract_document(sys.argv[1]).model_dump_json(indent=2))
