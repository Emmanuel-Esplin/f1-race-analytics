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
