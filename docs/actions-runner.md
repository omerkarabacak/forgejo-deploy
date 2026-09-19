# Optional Docker Actions runner

The runner is a separate Compose project in [runner/compose.yaml](../runner/compose.yaml).
It does not change the Forgejo web stack or publish any host ports. It uses
Forgejo Runner 13.0.0 and Docker 29.8.0 in a dedicated Docker-in-Docker (DinD)
container, with persistent Docker storage and a private Unix socket.

Choose the Forgejo host for a compact deployment, or follow the
[separate runner VM guide](runner-vm.md) to keep builds on another machine.
The same Compose file supports both. Run all commands on the **runner host**,
from its copy of this repository; the Forgejo server's `.env` is not required.

Register it for a **single trusted repository**. Jobs can control the DinD engine
and inspect data left by earlier jobs, but do not receive the Docker socket that
manages Forgejo and PostgreSQL. DinD itself is privileged and shares the host
kernel; this is not a VM security boundary. A separate VM isolates the runner
host from the Git server, but jobs still share persistent runner storage. Keep
this setup restricted to trusted workflows; see the
[upstream security guidance](https://forgejo.org/docs/latest/admin/actions/security/)
before accepting untrusted jobs. One job runs at a time; the DinD container is
limited to 3 CPUs and 5 GiB RAM. Allow additional memory for the runner, host OS,
and any other services on the same machine.

## Register and start

1. In the target repository, open **Settings → Actions → Runners → Create new
   runner**. Use a persistent runner (the default) for this daemon. Give each
   runner VM its own registration and save its UUID and token privately.
2. From the deployment directory, prepare the runner's configuration:

   ```sh
   install -d -m 0700 runner/state
   cp runner/config.example.yml runner/state/config.yml
   chmod 600 runner/state/config.yml
   ```

   Edit `runner/state/config.yml`: replace the example URL and runner UUID.
   Use the Forgejo server's full HTTPS URL, such as `https://git.example.com/`,
   reachable from this host and its job containers. Keep `insecure: false`.
   Store the runner token in `runner/state/token`, using a private editor or
   password manager. Do not place the token in shell history or the example
   file. Then set permissions for the runner's UID:

   ```sh
   chmod 600 runner/state/token
   sudo chown -R 1000:1000 runner/state
   docker compose -f runner/compose.yaml config --quiet
   docker compose -f runner/compose.yaml pull
   docker compose -f runner/compose.yaml up -d --wait --wait-timeout 180
   docker compose -f runner/compose.yaml logs --tail=50 runner
   ```

3. Check that the runner is online in the repository settings. Enable Actions
   in the repository's unit settings if necessary, then run a harmless workflow
   using `runs-on: ubuntu-latest` or `runs-on: ubuntu-24.04`.

The runner state, cache, and token are ignored by Git. The Ubuntu job image is
`ghcr.io/catthehacker/ubuntu:act-24.04`, a community image also described in
Forgejo's documentation. Its tag is refreshed for each job; pin a reviewed
digest in the configuration if reproducible job images are required. The runner
and DinD service images use explicit release versions.

## Verification and maintenance

On Ubuntu 24.04 with Forgejo 15.0.7, the runner passed real workflow jobs for
private checkout, nested Docker, and saving/restoring Actions caches. Application
workflows still require their own compatibility testing.

Verify checkout of a private repository, `docker version`, `docker compose
version`, a disposable `docker run --rm hello-world`, and both saving and
restoring an Actions cache. The runner shares DinD's network namespace so the
cache can be reached from nested job containers; it has no public listener.

```sh
docker compose -f runner/compose.yaml ps
docker compose -f runner/compose.yaml logs --tail=100 runner
docker compose -f runner/compose.yaml exec docker docker system df
```

Runner updates are manual. Stop the runner before replacing the DinD container
so its shared network namespace is recreated correctly:

```sh
docker compose -f runner/compose.yaml stop runner
docker compose -f runner/compose.yaml pull
docker compose -f runner/compose.yaml up -d --force-recreate --wait
```

Docker images, build caches, volumes, and runner caches consume disk over time.
Inspect usage and prune only the dedicated DinD engine while the runner is
stopped. Do not run cleanup against the host Docker engine. Do not use
`down --volumes` unless intentionally discarding the runner's Docker storage.
Back up `runner/state` securely or revoke and re-register the runner after loss.

## Migrating GitHub workflows and secrets

Forgejo Actions is familiar to GitHub Actions but has compatibility differences.
Audit each workflow before enabling deployments:

- Put Forgejo workflows in `.forgejo/workflows`. Use explicit action URLs when
  an action must come from GitHub; short `uses: owner/action@ref` names resolve
  against the server's configured action source.
- Container jobs reach service containers by their service names, not the
  runner's `127.0.0.1`. Adjust database and Redis URLs accordingly.
- A Docker command that bind-mounts a path resolves it inside the DinD container,
  not automatically inside the job container. Adapt such commands to share
  volumes or copy inputs; `docker build` can send its build context normally.
- Audit artifact actions, GitHub-specific API calls, runner groups, environment
  protections, and tests that need additional Linux capabilities. A generic
  Docker runner does not replace a live infrastructure runner.
- GitHub secret-list APIs return names and timestamps, not stored values.
  Re-enter originals securely, or use an explicitly authorized one-time GitHub
  workflow to send a reviewed set of secrets directly to the destination HTTPS
  API. Never print values or put them in logs, artifacts, or commits. Remove
  temporary transfer credentials and workflow branches when finished.
- Repository variables and environment protections require separate review;
  copying environment secrets into repository scope does not preserve GitHub's
  environment approval rules.

References: [runner installation](https://forgejo.org/docs/latest/admin/actions/installation/docker/),
[runner registration](https://forgejo.org/docs/latest/admin/actions/registration/),
[Docker inside Actions](https://forgejo.org/docs/latest/admin/actions/docker-access/),
[GitHub differences](https://forgejo.org/docs/v15.0/user/actions/github-actions/),
and [GitHub secret API](https://docs.github.com/en/rest/actions/secrets).
