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
