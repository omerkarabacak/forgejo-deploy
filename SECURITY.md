# Security policy

## Report a vulnerability privately

Do not open a public issue containing exploit details, credentials, private keys,
or sensitive deployment information.

If this repository has GitHub private vulnerability reporting enabled, open its
**Security → Advisories** page and choose **Report a vulnerability**. Otherwise,
use a private contact method published on the maintainer's GitHub profile. If no
private channel is available, open an issue asking for one without disclosing
the vulnerability or exploit details.

Include the affected commit or version, relevant component versions, impact,
reproduction steps, and a redacted example configuration. Do not send real
credentials or data from other users' repositories.

For vulnerabilities in Forgejo, Caddy, PostgreSQL, or Docker itself, follow the
affected upstream project's security reporting process. Report deployment
configuration issues here. No response-time or patch schedule is promised.

## Scope and updates

This repository is an independent deployment template. Security changes target
the current default branch; there are no separately maintained older release
branches. Operators are responsible for reviewing and applying upstream security
updates, protecting Docker access and secrets, and maintaining tested backups.

Container image versions are pinned and do not update automatically. Certificate
renewal does not update Forgejo, PostgreSQL, Caddy, Docker, or the host OS.

Before sharing diagnostics, remove credentials, tokens, private repository names,
personal details, and keys. Never publish `.env`, persistent volumes, `app.ini`,
database dumps, or backup archives. If a secret has been exposed, rotate it even
if the published copy is later removed.
