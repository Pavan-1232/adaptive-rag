# Security policy

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue or pull request.

Use GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**. Only the maintainer can see the report.

Please include:

- what the problem is and where (file, endpoint or feature);
- steps to reproduce, or a proof of concept;
- what an attacker could do with it.

Don't include real API keys or private documents in a report. Use made-up values.

You can expect an acknowledgement within 7 days. Once the problem is confirmed, I'll work on a fix and agree a disclosure date with you. Credit is given in the fix's notes unless you'd rather stay anonymous.

## Supported versions

Only the latest commit on `main` is supported. There are no released versions yet.

## Scope

Adaptive RAG is a local, single-user application. It is designed to run on your own machine and serve only `127.0.0.1` / `localhost`. Reports are especially welcome for:

- API key handling: keys reaching logs, traces, error messages, the browser, the database or the vector index;
- uploaded files: crashes or code execution from crafted PDF, DOCX or TXT files, and bypasses of the type and size checks;
- prompt injection: document text that changes the app's behaviour beyond the answer to the question;
- the local-only protections: Host and Origin checks, DNS rebinding;
- cloud models being used for a knowledge base that hasn't allowed them.

Running the app on a network-reachable address, or behind a public proxy, is outside the intended use. Findings that depend on that setup are still useful, but are lower priority.

Third-party dependencies are monitored with Dependabot. Known advisories that don't apply to how this project uses a dependency are recorded in [docs/PROGRESS.md](docs/PROGRESS.md).
