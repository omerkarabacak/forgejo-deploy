# Contributing

Bug reports, documentation fixes, and small, focused pull requests are welcome.
This repository is a deployment template; application bugs should be reported to
the relevant upstream project when they also occur outside this configuration.

## Report a problem

Search existing issues first. Include the host OS, CPU architecture, Docker and
Compose versions, pinned image versions, reproduction steps, expected behavior,
and relevant redacted logs. Explain any changes from the example configuration.

Do not attach `.env`, `app.ini`, backups, private keys, or unredacted
`docker compose config` output. For vulnerabilities, follow [SECURITY.md](SECURITY.md).

## Make a change

1. Fork the repository and create a branch for one change.
2. Update the relevant configuration and documentation together. Preserve the
   default deployment's Git SSH port 22 and automatic Let's Encrypt HTTPS.
3. Run the checks below and describe their results in your pull request.
4. Explain the problem, resulting behavior, and any migration steps or new
   requirements. Include upstream release notes when changing image versions.

Avoid adding personal infrastructure values or generated deployment data.
Document optional services without enabling them for every installation.

## Validate changes

Python 3.9+ and Docker Compose v2.20+ are required for repository validation:

```sh
python3 scripts/validate.py
```

Validation also renders the runner from an isolated directory without the
Forgejo stack or its environment, and checks that it needs no external Docker
networks, shared server volumes, or published ports. When changing the runner,
preserve both the same-host and [separate VM](docs/runner-vm.md) deployments.

With a locally configured `.env`, also validate the expanded Compose and Caddy
configuration:

```sh
docker compose config --quiet
docker compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

The optional container smoke test requires Bash, Python 3.9+, OpenSSL, curl,
a Docker daemon, and Compose v2.24.4+:

```sh
bash scripts/smoke-test.sh
```

It creates an isolated disposable Compose project with test values, dedicated
volumes, and loopback ports, then removes it. It checks application startup,
administrator creation, the SSH protocol greeting, and Caddy using internal test
TLS. Authenticated Git clone/push still requires a separate check. It does not use
your `.env`, bind production ports 22/80/443, or request a Let's Encrypt
certificate. The GitHub Actions workflow also runs this check.

Run deployment changes on a disposable Linux Docker host with dedicated volumes.
For public HTTPS testing, use a domain you control and the Let's Encrypt staging
endpoint first. Follow the [operations verification steps](docs/operations.md#verify-https-and-git-ssh)
and check account creation, SSH authentication, and Git clone/push as relevant to
the change.

Static checks and local container checks cannot prove public DNS or Let's Encrypt
reachability. State which checks ran and which need a real server; do not report
an unrun check as passing.

Dependabot is configured to propose container updates within the pinned major
versions and GitHub Actions updates weekly. These are reviewable pull requests;
they do not deploy changes or update running containers. Review major container
upgrades separately with their migration requirements.

## License

By submitting a contribution, you agree that it may be distributed under this
repository's [MIT License](LICENSE). Retain upstream notices when including
material from another project.
