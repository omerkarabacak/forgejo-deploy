# Operating the Forgejo stack

Run commands from the directory containing `compose.yaml`. Start with the
[README quick start](../README.md#quick-start) after preparing the host below.

## Prepare the server and DNS

Use a Linux server with Docker Engine and Docker Compose v2.20+ (or newer major).
This stack assumes a rootful Docker daemon and a domain pointed directly at the
server. Set a DNS A record such as `git.example.com` to the server's public IPv4
address. Publish an AAAA record only if IPv6 reaches this same stack on TCP ports
22, 80, and 443 too.

Allow inbound TCP **22, 80, 443** through the provider firewall and the host's
Docker-aware firewall rules. Forward those ports if the server is behind NAT.
UDP 443 is optional. Caddy also needs outbound DNS and HTTPS access for ACME.
Existing web servers cannot occupy the same address and ports as Caddy. Docker
published ports may bypass ordinary UFW rules; see the
[Docker firewall documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

Automatic certificate issuance depends on correct DNS and public ACME challenge
reachability. This configuration uses HTTP/TLS challenges; private-only servers
or networks that block both public challenge ports need a DNS challenge
configuration. See [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).

### Reserve port 22 for Forgejo

**Host administration SSH and Forgejo cannot listen on the same IP and port.**
Changing only `SSH_PORT` in Forgejo does not free the host port.

If the host currently uses port 22 for administration:

1. Keep the current session open and make sure you have console/recovery access.
2. Configure the host's SSH service to additionally listen on another port, for
   example **2222**, and allow it through the host/provider firewall.
3. Verify a new, separate login with `ssh -p 2222 your-user@server-address`.
4. Only after that succeeds, remove the host service's port 22 listener. Check
   for systemd socket activation too: the socket can own port 22 independently
   of the `sshd_config` settings.
5. Verify that TCP port 22 is free before starting Forgejo.

On Linux, inspect listeners with:

```sh
sudo ss -ltnp '( sport = :22 or sport = :80 or sport = :443 )'
```

The exact SSH service configuration depends on the server's OS. This project
does not modify the host's SSH service.

If the server has a separate interface IP for Forgejo, you can keep
administration SSH on port 22 of the other IP: change Forgejo's published mapping
in `compose.yaml` to `"SERVER_INTERFACE_IP:22:22"`, and ensure the host SSH
listener binds only its administration IP. A wildcard listener on `0.0.0.0`
or `::` can still cause a conflict. The DNS record must lead to Forgejo's IP.

The stack uses Forgejo's standard image with OpenSSH, so `22:22` publishes the
actual SSH listener. `SSH_PORT=22` makes Forgejo advertise matching clone URLs.
The separate embedded SSH server stays disabled.

## Configuration and accounts

The `.env` file supplies the domain, ACME email, and database password. A hostname
must have no scheme, port, or path. Missing required settings cause Compose to
fail before starting containers.

The database password is supplied to PostgreSQL and Forgejo and is also stored
in the persistent `app.ini`; protect these files and their backups.
Administrators with Docker access can inspect container environment variables.
Use `docker compose config --quiet` to validate without printing expanded values.

Create the first administrator using the command in the
[quick start](../README.md#2-validate-and-start-forgejo). Run account creation
once; the same username cannot be created again. The command uses Forgejo's
[administrator CLI](https://forgejo.org/docs/latest/admin/command-line/).

To enable public registration after creating the administrator, set
`DISABLE_REGISTRATION=false` in `.env` and run `docker compose up -d` again.
Public registration permits anyone to create an account. Keeping registration
disabled does not hide public repositories; create repositories as private when
their contents should require authorization.

SMTP and Actions runners are separate configuration choices. Email delivery,
including password reset mail, needs SMTP setup. CI jobs need a separately
deployed and registered runner; this stack does not execute them on its own.

## Verify HTTPS and Git SSH

Use your actual domain in these commands:

```sh
docker compose ps
curl -I http://git.example.com
curl --fail https://git.example.com/api/healthz
```

Expect an HTTP-to-HTTPS redirect and a successful HTTPS health response. Caddy
requests the certificate in the background, so container startup can finish
before HTTPS is ready. The `caddy_data` volume preserves certificates and ACME
account keys across restarts.

Add your public SSH key in Forgejo's account settings. Confirm the server's
SSH host key fingerprint through your trusted administration connection:

```sh
docker compose exec forgejo ssh-keygen -lf /data/ssh/ssh_host_ed25519_key.pub
```

Then, from your workstation:

```sh
ssh -T git@git.example.com
git clone git@git.example.com:YOUR_USER/YOUR_REPOSITORY.git
```

Check the fingerprint at first connection. Successful SSH authentication returns
a Forgejo greeting explaining that shell access is unavailable; it may return a
nonzero exit code despite successful authentication. No `-p` option or port
number in the clone URL is needed. SSH uses persisted host keys independently
of the Let's Encrypt certificate used for HTTPS.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Forgejo cannot publish port 22 | Inspect listeners with `ss`; check administrative `sshd` and systemd socket activation. |
| HTTPS certificate is not issued | Read `docker compose logs --tail=100 caddy`; check DNS A/AAAA records, firewall/NAT, port conflicts, and restrictive CAA records. |
| Database or Forgejo remains unhealthy | Run `docker compose ps` and read `docker compose logs --tail=100 db forgejo`; check available disk and configuration. |
| SSH authentication fails | Confirm the public key is added to your Forgejo account, use the `git` SSH user, and verify DNS points to this host. |
| Database login fails after editing `.env` | An existing database retains its previous password; coordinate password rotation in PostgreSQL and Forgejo. |

Redact credentials, tokens, private repository names, personal details, and
private keys before sharing logs in an issue. Do not post `.env` or `app.ini`.

## Persistent storage and backups

Named volumes persist across `docker compose down` and container recreation.
**Do not use `docker compose down -v` or prune these volumes unless you intend
to erase the installation.** With the default project name, the volumes are:

| Volume | Contents |
| --- | --- |
| `forgejo_forgejo_data` | Repositories, uploads, LFS data, app.ini, secrets, SSH keys |
| `forgejo_postgres_data` | PostgreSQL data files |
| `forgejo_caddy_data` | Certificates, private keys, ACME account state |
| `forgejo_caddy_config` | Caddy runtime configuration |

Before an upgrade, stop Forgejo to prevent repository and database writes,
then capture a PostgreSQL dump and an archive/snapshot of `forgejo_data` from
the same stopped period. Also preserve `.env`, the Compose/Caddy configuration,
and Caddy's volumes. For example, the database portion is:

```sh
mkdir -p backups
chmod 700 backups
docker compose stop forgejo
(umask 077; docker compose exec -T db pg_dump -U forgejo -d forgejo -Fc > backups/forgejo-db.dump)
# Keep Forgejo stopped while you archive/snapshot forgejo_data and the other files.
# The database dump alone is not a complete backup.
docker compose up -d --wait --wait-timeout 180
```

Check that each backup command succeeds before continuing. Use a unique backup
directory/file for each run, copy complete backups off the server, and test a
restore into separate volumes. Treat every backup as sensitive. Do not copy live
PostgreSQL data files as a substitute for a consistent dump or database-aware
snapshot. This repository does not schedule backups automatically.

## Upgrades and configuration reloads

Image versions are explicit so upgrades can be reviewed. Certificate renewal is
automatic; image upgrades are performed by the operator. Review upstream release
notes and the [Forgejo release schedule](https://forgejo.org/docs/latest/admin/release-schedule/)
before selecting a new version.

Take a complete backup, update image tags in `compose.yaml`, then run:

```sh
docker compose pull
docker compose up -d --wait --wait-timeout 180
```

Repeat the HTTPS and Git verification after upgrading. Follow the
[Forgejo upgrade guide](https://forgejo.org/docs/latest/admin/upgrade/) for major
version transitions. PostgreSQL major upgrades require a database migration;
changing its image tag alone is insufficient. Changing `POSTGRES_PASSWORD` in
`.env` also does not change the password in an existing database; coordinate
database password rotation with Forgejo configuration.

For a Caddyfile-only change, reload it with:

```sh
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

For `.env` changes use `docker compose up -d` so the container environment is
recreated. If testing ACME repeatedly, select the staging endpoint in `.env`;
staging certificates are deliberately untrusted. Switch back to the production
endpoint and recreate Caddy for the real installation. Caddy configuration
validation alone does not prove public DNS reachability or issue a certificate.

### Upgrading from Forgejo 15 to 16

The template pins Forgejo **16.0.4**, a stable release supported until
29 October 2026. This is a major upgrade from the previous 15.0.7 LTS pin.
Review the [16.0 announcement](https://forgejo.org/2026-07-release-v16-0/)
and [16.0.4 release notes](https://codeberg.org/forgejo/forgejo/src/branch/forgejo/release-notes-published/16.0.4.md).

Let active Actions jobs finish, pause the runner, and flush the server queues:

```sh
docker compose -f runner/compose.yaml stop runner # If the optional runner is installed.
docker compose exec --user git forgejo forgejo --config /data/gitea/conf/app.ini manager flush-queues --timeout 5m
```

Then stop Forgejo and take the complete backup described above. Keep the old
Compose configuration with that backup. Pull and start only the Forgejo service
after updating its image tag:

```sh
docker compose pull forgejo
docker compose up -d --no-deps --wait --wait-timeout 180 forgejo
docker compose exec --user git forgejo forgejo --config /data/gitea/conf/app.ini doctor check --all --log-file /tmp/forgejo-doctor.log
docker compose -f runner/compose.yaml start runner # If installed and stopped above.
```

The database migrates during startup. A rollback requires restoring the matching
database dump and Forgejo data backup with the old image; changing the image tag
back alone is not a safe downgrade.

The template already sets explicit trusted proxy networks, as required by the
new container defaults. HTTP mirrors must use their final URL because redirects
are no longer followed. Review scheduled workflows that use `forgejo.ref` and
API integrations that consume a pull request's `url` field, whose behavior was
corrected in version 16. Existing repository hooks can remain in place; upstream's
hook-file cleanup is optional. Repeat authenticated Git push/clone, HTTPS, and an
Actions job after upgrading.
