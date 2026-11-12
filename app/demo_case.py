"""Static demo case for the review dashboard. Not produced by the pipeline."""

DEMO_CASE = {
    "case_id": "DEMO-SAMPLE",
    "finding": "UNAGREED-FEE",
    "delta": 3000.0,
    "evidence": [
        {
            "doc": "inv-2041.pdf",
            "page": 1,
            "ref": "line 4: Freight surcharge, 3,000.00",
        },
        {
            "doc": "po-4471.pdf",
            "page": 1,
            "ref": "no freight line (PO total 15,000.00)",
        },
        {
            "doc": "msa-acme.pdf",
            "page": 6,
            "ref": "clause 4.2: freight is included in the unit price",
        },
    ],
    "proposed_action": ["HOLD_INVOICE", "DRAFT_SUPPLIER_MESSAGE"],
    "requires_human_approval": True,
}
