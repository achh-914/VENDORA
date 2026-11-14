<p align="center">
  <img src="docs/assets/logo.svg" width="360" alt="Vendora">
</p>

<h3 align="center">Procurement investigations done by AI agents. Decided by people.</h3>

<p align="center">
  OCR tools read invoices. Vendora works out why an invoice disagrees with its purchase order and contract,
  shows the evidence, and holds the payment until a person decides.
</p>

<p align="center">
  <img alt="status" src="https://img.shields.io/badge/status-early%20development-e11d48?style=flat-square">
  <img alt="python" src="https://img.shields.io/badge/python-3.12-3776ab?style=flat-square">
  <img alt="fastapi" src="https://img.shields.io/badge/API-FastAPI-009688?style=flat-square">
  <img alt="llm" src="https://img.shields.io/badge/LLM-Gemini-4285f4?style=flat-square">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-16a34a?style=flat-square">
  <img alt="schema" src="https://github.com/achh-914/VENDORA/actions/workflows/schema.yml/badge.svg">
  <a href="https://github.com/achh-914/VENDORA/actions/workflows/ci.yml"><img src="https://github.com/achh-914/VENDORA/actions/workflows/ci.yml/badge.svg" alt="ci"></a>
</p>

---

## Demo

https://github.com/user-attachments/assets/20be62a8-5ab8-4a64-ac43-f9b70f1c7425

---

## The problem

A company receives an invoice. Three documents disagree:

| Document | What it says |
|---|---|
| Invoice | **$18,000**, with a freight line |
| Purchase order | **$15,000**, no freight line |
| Contract | Different pricing rules, and a clause about delivery costs |

*(Illustrative numbers.)*

An analyst opens all three, finds the $3,000 gap, works out why, writes to the supplier, and blocks payment in the meantime. This happens thousands of times a year, and every case is slow and easy to get wrong.

Vendora does the investigation and hands the analyst a **case file**: what differs, why, which page and clause prove it, and what to do next.

---

## What Vendora does

| Capability | Question it answers | Status |
|---|---|---|
| **Extract** | What do these documents actually say? | Done (M1), scored with Gemini |
| **Match** | Where do they disagree? | Done (M2), invoice against PO |
| **Investigate** | Why, and which line or clause proves it? | Done (M3), cites the contract clause for unagreed fees |
| **Resolve** | What is the safest next step? | Done (M3), actions are proposed and simulated |
| **Escalate** | Has a person approved it? | Done (M5), review dashboard |
| **Audit** | Who decided what, based on which evidence? | Done (M5), hash-chained trail |
| **Evaluate** | How often is the system right? | Done (M4), 80 synthetic cases and a 3-PDF extraction run |

---

## Architecture

<p align="center">
  <img src="docs/assets/architecture.svg" alt="Vendora architecture: documents flow through extraction, an orchestrator with an evidence store, matching and investigation agents, a supervisor, and a human approval step, with an audit trail underneath." width="100%">
</p>

> The diagram shows the target design. Solid boxes are the MVP, dashed boxes are planned.

**What runs today.** A fixed workflow: Extraction, then Matching, then Investigation, then a review step where a person decides. The Supervisor agent, the evidence store (PostgreSQL with pgvector) and dynamic routing are planned. See the [Roadmap](#roadmap).

**Why a fixed workflow first.** Dynamic routing (letting the system choose which agent acts) comes after the fixed version is measured and works.

---

## Example: one case, end to end

1. **Extract.** Pull totals, line items and terms from the invoice, PO and contract, keeping the page of each value.
2. **Match.** Compare the invoice with the PO. Flag the freight line that appears on the invoice only.
3. **Investigate.** Search the contract. Find the delivery clause that says freight is included in the unit price.
4. **Review.** The case file goes to the review dashboard with a proposed action. A person decides. Every step is logged.

Example case file (illustrative numbers):

```json
{
  "case_id": "CASE-0001",
  "finding": "UNAGREED-FEE",
  "delta": 3000.00,
  "evidence": [
    { "doc": "invoice.pdf",  "page": 1, "ref": "line 4: Freight surcharge, $3,000" },
    { "doc": "po-4471.pdf",  "page": 1, "ref": "no freight line, total $15,000" },
    { "doc": "contract.pdf", "page": 6, "ref": "clause 4.2: freight included in unit price" }
  ],
  "proposed_action": ["HOLD_INVOICE", "DRAFT_SUPPLIER_MESSAGE"],
  "requires_human_approval": true
}
```

---

## Review dashboard

Start the server and open `http://127.0.0.1:8000/review`. For each case the page shows the difference, the evidence (document, page and clause), the proposed actions, and the decision of a person. Every event is appended to a hash-chained audit trail, and the page shows whether the chain still verifies.

The dashboard also ships with one demo case, `DEMO-SAMPLE`, labelled as demo data. Proposed actions (hold the invoice, draft a message) are simulated: nothing is sent, held or paid.

The CLI can submit the case files it produces to the dashboard. See `python -m app.cli analyze --help`.

---

## Discrepancy types

| Tag | What it detects |
|---|---|
| `PRICE-MISMATCH` | Invoice total or unit price differs from the PO |
| `UNAGREED-FEE` | A charge (freight, handling, surcharge) that is not in the PO or contract |
| `QTY-VARIANCE` | Billed quantity differs from the quantity ordered or received |
| `DUPLICATE-LINE` | The same line item billed twice |
| `TERMS-CONFLICT` | Payment terms or pricing rules contradict the contract |

`TERMS-CONFLICT` is defined in the schema but is not covered by the evaluation yet.

---

## Quick start

```bash
git clone https://github.com/achh-914/VENDORA.git
cd VENDORA
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,gemini]"
```

Run the tests and the offline evaluation (no API key needed):

```bash
pytest
python eval/run_eval.py
```

Analyze pre-extracted documents (no API key needed):

```bash
python -m app.cli analyze \
  --invoice tests/fixtures/invoice.json \
  --po tests/fixtures/po.json \
  --contract tests/fixtures/contract.json
```

Analyze the sample PDFs (needs a free Gemini key from Google AI Studio):

```bash
export GEMINI_API_KEY=your_key_here
export VENDORA_PROVIDER=gemini
python -m app.cli analyze \
  --invoice data/samples/inv-2041.pdf \
  --po data/samples/po-4471.pdf \
  --contract data/samples/msa-acme.pdf
```

Open the review dashboard:

```bash
uvicorn app.main:app --reload
# http://127.0.0.1:8000/review      API docs: http://127.0.0.1:8000/docs
```

Use synthetic documents only. A free API tier may use inputs to improve the provider's products.

---

## Design principles

- **A person decides about money.** Vendora proposes. It never approves or pays on its own.
- **Evidence or it did not happen.** Every conclusion points to a document, page and clause.
- **Tamper-evident audit trail.** Every step is appended to a hash chain, so edits to history are detectable.
- **Simulated actions by default.** Holding an invoice or emailing a supplier is simulated in the MVP.
- **Fixed before dynamic.** Get one workflow right and measured before adding routing.
- **Measured, not assumed.** Quality is scored against cases with known answers.

---

## Evaluation

Cases are synthetic documents with deliberate errors, so each one has a known correct answer.

**Matching and investigation** (offline, no LLM): 80 generated cases (40 basic, 40 hard), fixed seed. This run is also part of the test suite, so a regression fails CI.

**Extraction** (real model): the three sample PDFs, scored field by field.

| Metric | Result |
|---|---|
| Detection, basic cases (5 error types) | 40/40 (100%) |
| Detection, hard cases | 40/40 (100%) |
| Amount (delta) accuracy | 64/64 (100%) |
| Fee clause citation (clause 4.2, page 2) | 32/32 (100%) |
| Case files requiring human approval | 32/32 (100%) |
| Extraction accuracy (3 PDFs, 26 fields) | 26/26 (100%), Gemini |
| Cost per case | $0.00 (offline matching, free tier extraction) |

Hard matching cases cover several errors in one invoice, two unagreed fees, shuffled line order, agreed fees that must not be flagged, and decimal rounding.

**Read this carefully.** These are small, clean, synthetic inputs, and the extraction score comes from a single run on three text PDFs (one request needed a retry after a temporary server error). It shows the pipeline works end to end. It does not show real-world accuracy. Scanned documents, other layouts and languages are not covered. Gemini is the default provider and the one that was scored. Claude is supported (`VENDORA_PROVIDER=claude`) but has not been scored yet.

Run it yourself: `python eval/run_eval.py` (matching) and `python eval/run_extraction_eval.py` (extraction, needs an API key).

---

## Roadmap

- [x] **M1: Extraction.** Structured extraction from invoice, PO and contract, with page references (scored on 3 synthetic PDFs with Gemini)
- [x] **M2: Matching.** Cross-document comparison and discrepancy detection
- [x] **M3: Investigation.** Root cause with cited evidence, proposed resolution, audit log
- [x] **M4: Evaluation.** 80 synthetic cases and automated scoring, plus a field-level extraction score
- [x] **M5: Demo.** Review dashboard with the human approval flow and audit view
- [ ] **Later:** Supervisor agent, PostgreSQL storage and evidence store, negotiation agent, compliance rules, dynamic routing, exports, extraction scoring on harder and scanned documents, scoring Claude

---

## Project structure

```
vendora/
├── app/
│   ├── main.py         FastAPI application and review routes
│   ├── server.py       alternative app entry point
│   ├── cli.py          command line: analyze
│   ├── review.py       review dashboard API
│   ├── store.py        review store with a hash-chained audit log
│   ├── schemas.py      case file and discrepancy models
│   ├── demo_case.py    static demo case for the dashboard
│   ├── static/         review dashboard page
│   └── agents/         extraction, matching, investigation
├── eval/               case generation and scoring scripts
├── scripts/            data generation and evaluation helpers
├── data/samples/       synthetic invoice, PO and contract (PDF)
├── tests/              unit tests and JSON fixtures (run in CI)
├── db/                 PostgreSQL schema (not used by the app yet)
├── docs/               design notes and assets
├── docker-compose.yml  PostgreSQL with pgvector
└── .env.example
```

---

## Scope and limitations

- Early-stage project, not production-ready.
- Synthetic documents only. No real company data.
- Actions are simulated. Nothing is sent, held or paid.
- The review store persists to a local JSON file. PostgreSQL is defined in `db/` but the app does not use it yet.
- Matching compares the invoice with the PO. The contract is used to explain unagreed fees; other discrepancy types are not explained from the contract yet.
- There is no Supervisor agent yet: every case goes to a person.
- Extraction was scored on three text PDFs, with Gemini only.

## Contributing

Feedback and ideas are welcome. Open an issue before proposing larger changes.


## License

Vendora is proprietary software.
All rights reserved.

See [PROPRIETARY-NOTICE.txt](PROPRIETARY-NOTICE.txt).
