# Security Policy

## Project status

Vendora is an early-stage project and is **not production-ready**. It is built and tested on synthetic documents only. Do not use it with real financial data until it has had a proper security review.

## Supported versions

Only the latest commit on `main` is supported.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately in one of these ways:

- Use GitHub's [private vulnerability reporting](https://github.com/achh-914/VENDORA/security/advisories/new) on this repository.
- Email **meriemachh5@gmail.com** with the subject `Vendora security`.

Include:

- A description of the issue and its impact
- Steps to reproduce
- Affected files or versions, if known

You can expect an acknowledgement within a few days. Please give a reasonable amount of time to fix the issue before disclosing it publicly.

## What counts

Examples of issues worth reporting:

- Leaked secrets or credentials in the code or history
- Prompt injection through document content that makes an agent skip human approval
- Access to documents or cases belonging to another user
- Unsafe handling of uploaded files
- Missing or bypassable audit logging

## Handling secrets

- Never commit `.env`, API keys, or cloud credentials.
- If you find a committed secret, report it and rotate the key immediately. Removing it from the history is not enough.

## Design safeguards

- Actions are simulated in the MVP. Nothing is paid, sent, or approved automatically.
- Every agent step and decision is written to an audit log.
- Document content is treated as untrusted input, never as instructions.
