#!/usr/bin/env bash
# Exercise the production images with disposable data and an internal TLS CA.
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
for command in docker python3 openssl curl; do
  command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 1; }
done

# Compose --wait bounds health checks; this also bounds image pulls and CLI calls.
bounded() {
  python3 - "$@" <<'PY'
import subprocess
import sys

try:
    result = subprocess.run(sys.argv[2:], timeout=int(sys.argv[1]))
except subprocess.TimeoutExpired:
    print("Smoke-test command timed out.", file=sys.stderr)
    sys.exit(124)
sys.exit(result.returncode)
PY
}

export FORGEJO_DOMAIN=forgejo.test
export ACME_EMAIL=ci@example.invalid
# Defense in depth: even an accidental use of the production file has no real CA.
export ACME_CA=https://acme.invalid/directory
export POSTGRES_PASSWORD
POSTGRES_PASSWORD=$(openssl rand -hex 32)
export DISABLE_REGISTRATION=true
export FORGEJO_ADMIN_PASSWORD
FORGEJO_ADMIN_PASSWORD=$(openssl rand -hex 32)

project="forgejo-smoke-$(openssl rand -hex 8)"
temporary_dir=$(mktemp -d "${TMPDIR:-/tmp}/forgejo-smoke.XXXXXXXX")
chmod 700 "$temporary_dir"
compose=(docker compose --env-file /dev/null --project-name "$project"
  -f compose.yaml -f tests/compose.ci.yaml)

cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 )); then
    bounded 20 "${compose[@]}" ps --all || true
    bounded 20 "${compose[@]}" logs --no-color --tail 100 || true
  fi
  # The random project name scopes deletion to this run's containers and volumes.
  bounded 60 "${compose[@]}" down --volumes --remove-orphans --timeout 10 || status=1
  rm -rf -- "$temporary_dir"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Starting disposable integration stack: $project"
bounded 600 "${compose[@]}" up --detach --wait --wait-timeout 180
bounded 20 "${compose[@]}" exec -T forgejo \
  curl --fail --silent --show-error http://127.0.0.1:3000/api/healthz >/dev/null

echo "Creating the initial administrator with the Forgejo CLI"
bounded 30 "${compose[@]}" exec -T --user git -e FORGEJO_ADMIN_PASSWORD forgejo \
  sh -c 'exec forgejo --config /data/gitea/conf/app.ini admin user create \
    --username ci-admin --email ci-admin@example.invalid --admin \
    --password "$FORGEJO_ADMIN_PASSWORD" --must-change-password=false'

https_address=$(bounded 20 "${compose[@]}" port caddy 443)
https_port=${https_address##*:}
ssh_address=$(bounded 20 "${compose[@]}" port forgejo 22)
ssh_port=${ssh_address##*:}
[[ "$https_address" == 127.0.0.1:* && "$ssh_address" == 127.0.0.1:* ]] || {
  echo "Test ports must bind only to loopback." >&2
  exit 1
}

# Caddy may still be provisioning its internal CA after its container starts.
deadline=$((SECONDS + 60))
until bounded 10 "${compose[@]}" cp \
  caddy:/data/caddy/pki/authorities/local/root.crt "$temporary_dir/root.crt" 2>/dev/null \
  && curl --fail --silent --show-error --noproxy '*' \
    --connect-timeout 2 --max-time 5 \
    --cacert "$temporary_dir/root.crt" \
    --resolve "forgejo.test:$https_port:127.0.0.1" \
    "https://forgejo.test:$https_port/api/healthz" > "$temporary_dir/health.json" 2>/dev/null; do
  if (( SECONDS >= deadline )); then
    echo "Caddy did not serve a healthy Forgejo response with trusted TLS within 60 seconds." >&2
    exit 1
  fi
  sleep 2
done

python3 - "$ssh_port" <<'PY'
import socket
import sys

with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=10) as connection:
    with connection.makefile("rb") as stream:
        banner = stream.readline(256)
if not banner.startswith(b"SSH-2.0-"):
    sys.exit("Forgejo did not return an SSH protocol greeting.")
print("Forgejo SSH protocol greeting verified.")
PY

echo "Passed: service health, administrator creation, trusted HTTPS proxy, and SSH listener."
