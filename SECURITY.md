# Security

Report a vulnerability through GitHub's private vulnerability reporting
("Security" tab, "Report a vulnerability"), not a public issue.

## What protects this repo

- No secrets in code: AWS access uses short-lived credentials (`aws login` locally, IAM roles in
  AWS). gitleaks runs on every push, and GitHub push protection blocks known secret formats.
- Dependencies are locked (`requirements.lock`) and audited with pip-audit in CI. Dependabot
  proposes updates after a 7-day cooldown, so a freshly published malicious release is not picked
  up straight away.
- GitHub Actions are pinned to commit SHAs, run with read-only tokens, and are checked by zizmor.
- AWS: the bucket blocks public access and refuses non-TLS requests; each Lambda has its own role
  limited to the prefixes it needs; Athena has a per-query scan cap and a budget alert exists.
- The Lambda image is scanned by ECR on every push. Open findings are reviewed before deploying.

## Known findings

| Date | Finding | Where | Status |
| --- | --- | --- | --- |
| 2026-11-08 | CVE-2026-114406 (Medium): weak-key eMudhra roots in the CA store | `ca-certificates` in the AL2023 base image | No fixed package yet. The pipeline's HTTP clients use certifi's bundle, not the system store. Rebuild when AL2023 ships a fix. |
| 2026-11-08 | CVE-2026-76781 (Medium): libxml2 NULL dereference on crafted XML catalogs | `libxml2` in the AL2023 base image | No fixed package yet. The pipeline parses no XML. Rebuild when fixed. |
