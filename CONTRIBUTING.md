# Contributing to Vendora

Thanks for your interest. Vendora is in early development, so the most useful contributions right now are feedback, test cases, and focused fixes.

## Before you start

- Open an **issue** before working on anything larger than a small fix, so we can agree on the approach.
- Check the [Roadmap](README.md#roadmap) to see what is in scope for the current milestone.
- By contributing, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ground rules

- **Synthetic data only.** Never commit real invoices, contracts, supplier names, or any company data.
- **No secrets.** Never commit API keys, tokens, or `.env` files. Use `.env.example` for variable names.
- **Humans approve.** Do not add code that approves, pays, or sends anything without a human approval step.
- **Evidence required.** Agent conclusions must reference a document, page, and clause.

## Development setup

```bash
git clone https://github.com/achh-914/VENDORA.git
cd VENDORA
cp .env.example .env        # add ANTHROPIC_API_KEY
docker compose up -d        # PostgreSQL with pgvector
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # available once packaging is added
```

> The setup will be filled in as the first milestone lands.

## Workflow

1. Fork the repo and create a branch from `main`: `feature/short-description` or `fix/short-description`.
2. Make a focused change. One purpose per pull request.
3. Add or update tests. Changes to agent behavior should also update the evaluation cases in `eval/`.
4. Run the tests and the linter before pushing.
5. Open a pull request and describe what changed and why.

## Commit messages

Use short, imperative messages with a prefix:

```
feat: add freight line detection to matching agent
fix: keep page reference when extraction retries
docs: clarify evaluation metrics
test: add duplicate-line cases
```

## Adding evaluation cases

Evaluation cases are one of the most valuable contributions. A case includes:

- Synthetic invoice, PO, and contract documents
- The expected discrepancy type (see [Discrepancy types](README.md#discrepancy-types))
- The expected root cause and the evidence that proves it

Keep documents realistic but fictional.

## Reporting bugs

Open an issue with the steps to reproduce, what you expected, and what happened. Remove any sensitive data first. For security problems, follow [SECURITY.md](SECURITY.md) instead.
