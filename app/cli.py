"""Command line entry point: extract, match, investigate, then wait for a human.

Nothing is executed. Actions are only proposed and need human approval.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from google.genai import errors as genai_errors

from app.agents.extraction import ExtractedDocument, extract_document
from app.agents.investigation import investigate
from app.agents.matching import CURRENCY_SYMBOLS, match_documents
from app.schemas import CaseFile

RETRIES = 3


def load_document(path: str) -> ExtractedDocument:
    """Read a saved extraction (.json) or extract a PDF with the LLM."""
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(path)
    if file.suffix.lower() == ".json":
        return ExtractedDocument.model_validate_json(file.read_text())

    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            return extract_document(file)
        except (genai_errors.ServerError, genai_errors.ClientError) as exc:
            if isinstance(exc, genai_errors.ClientError) and exc.code != 429:
                raise  # a real client error (bad key, bad model): do not retry
            last_error = exc
            if attempt < RETRIES:
                print(
                    f"  {file.name}: {type(exc).__name__}, retry {attempt}/{RETRIES - 1}",
                    file=sys.stderr,
                )
                time.sleep(2**attempt)
    raise last_error


def _currency_label(doc: ExtractedDocument) -> str:
    raw = (doc.currency or "").strip()
    return CURRENCY_SYMBOLS.get(raw, raw.upper())


def render_case(case: CaseFile, currency: str) -> str:
    lines = [f"x {case.case_id}: {case.finding.value} ({currency} {case.delta:,.2f})".rstrip()]
    for item in case.evidence:
        lines.append(f"    {item.doc:<16} p.{item.page}  {item.ref}")
    actions = ", ".join(action.value for action in case.proposed_action)
    status = "Waiting for human approval." if case.requires_human_approval else ""
    lines.append(f"! Proposed: {actions}. {status}".rstrip())
    return "\n".join(lines)


def analyze(args: argparse.Namespace) -> int:
    print("Extracting documents...", file=sys.stderr)
    invoice = load_document(args.invoice)
    po = load_document(args.po)
    contract = load_document(args.contract)

    findings = match_documents(invoice, po)
    cases = [
        investigate(finding, contract, case_id=f"CASE-{index:04d}")
        for index, finding in enumerate(findings, start=1)
    ]

    if args.json:
        print(json.dumps([case.model_dump(mode="json") for case in cases], indent=2))
        return 0

    print(f"Extracted 3 documents: {invoice.doc_id}, {po.doc_id}, {contract.doc_id}")
    if not cases:
        print("No discrepancies found.")
        return 0
    print(f"{len(cases)} discrepancy(ies) found")
    currency = _currency_label(invoice)
    for case in cases:
        print()
        print(render_case(case, currency))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vendora")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("analyze", help="investigate an invoice against its PO and contract")
    cmd.add_argument("--invoice", required=True, help="invoice PDF or extracted JSON")
    cmd.add_argument("--po", required=True, help="purchase order PDF or extracted JSON")
    cmd.add_argument("--contract", required=True, help="contract PDF or extracted JSON")
    cmd.add_argument("--json", action="store_true", help="print case files as JSON")
    cmd.set_defaults(func=analyze)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
