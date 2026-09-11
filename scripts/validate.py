#!/usr/bin/env python3
"""Validate the deployment with disposable values; never load a local .env."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("FORGEJO_DOMAIN", "ACME_EMAIL", "POSTGRES_PASSWORD")
TEST_VALUES = {
    "FORGEJO_DOMAIN": "git.example.com",
    "ACME_EMAIL": "ci@example.invalid",
    "POSTGRES_PASSWORD": "disposable-validation-value",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def render(values):
    # Ignore deployment/Compose overrides inherited from the operator's shell.
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("FORGEJO_", "POSTGRES_", "ACME_", "COMPOSE_"))
        and key != "DISABLE_REGISTRATION"
    }
    environment.update(values)
    return subprocess.run(
        ["docker", "compose", "--env-file", os.devnull, "-f", "compose.yaml",
         "--project-name", "forgejo-validation", "config", "--format", "json"],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30,
    )


def configuration():
    result = render(TEST_VALUES)
    require(result.returncode == 0, "Compose validation failed: " + result.stderr)
    config = json.loads(result.stdout)
    services = config["services"]
    require(set(services) == {"caddy", "forgejo", "db"}, "Unexpected default services")
    expected_ports = {
        "caddy": {(80, "80", "tcp"), (443, "443", "tcp"), (443, "443", "udp")},
        "forgejo": {(22, "22", "tcp")},
        "db": set(),
    }
    for name, service in services.items():
        ports = {(port["target"], port["published"], port["protocol"])
                 for port in service.get("ports", [])}
        require(ports == expected_ports[name], f"Unexpected public ports for {name}")
        require(re.search(r":\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?$", service["image"]),
                f"Pin {name} to an explicit image version")

    settings = services["forgejo"]["environment"]
    require(settings["FORGEJO__server__ROOT_URL"] == "https://git.example.com/",
            "Forgejo must advertise the configured HTTPS domain")
    require(settings["FORGEJO__server__SSH_DOMAIN"] == "git.example.com"
            and settings["FORGEJO__server__SSH_PORT"] == "22",
            "Git SSH clone URLs must use the configured domain and port 22")
    require(settings["FORGEJO__security__INSTALL_LOCK"] == "true"
            and settings["FORGEJO__service__DISABLE_REGISTRATION"] == "true",
            "Default public installer and registration must be disabled")
    require(settings["FORGEJO__database__PASSWD"]
            == services["db"]["environment"]["POSTGRES_PASSWORD"]
            == TEST_VALUES["POSTGRES_PASSWORD"], "Database passwords must agree")
    require(config["networks"]["database"]["internal"] is True,
            "Database network must be internal")
    require(set(services["caddy"]["networks"]) == {"proxy"}
            and set(services["db"]["networks"]) == {"database"},
            "Caddy and PostgreSQL must use separate networks")
    for service, target in (("forgejo", "/data"), ("db", "/var/lib/postgresql/data"),
                            ("caddy", "/data"), ("caddy", "/config")):
        require(any(volume["target"] == target and volume["type"] == "volume"
                    for volume in services[service]["volumes"]),
                f"{service}:{target} must use a persistent named volume")

    for key in REQUIRED:
        for empty in (False, True):
            values = dict(TEST_VALUES)
            if empty:
                values[key] = ""
            else:
                values.pop(key)
            missing = render(values)
            require(missing.returncode != 0 and key in missing.stderr,
                    f"Compose must reject a missing or empty {key}")
    alternate = render(TEST_VALUES | {
        "DISABLE_REGISTRATION": "false",
        "ACME_CA": "https://acme-staging-v02.api.letsencrypt.org/directory",
    })
    require(alternate.returncode == 0, "Optional configuration could not be rendered")
    alternative = json.loads(alternate.stdout)["services"]
    require(alternative["forgejo"]["environment"]["FORGEJO__service__DISABLE_REGISTRATION"]
            == "false", "Registration override must work")
    require(alternative["caddy"]["environment"]["ACME_CA"]
            == "https://acme-staging-v02.api.letsencrypt.org/directory",
            "ACME staging override must work")
    print("PASS: Compose, port exposure, persistence, required values, and optional settings")


def repository_files():
    example = dict(line.split("=", 1) for line in (ROOT / ".env.example").read_text().splitlines()
                   if line and not line.startswith("#") and "=" in line)
    require(all(example.get(key) == "" for key in REQUIRED),
            ".env.example must leave domain, email, and database password blank")
    markdown = list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))
    for path in markdown:
        for link in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", path.read_text()):
            if ":" in link or link.startswith("#"):
                continue
            destination = unquote(link.split("#", 1)[0])
            require((path.parent / destination).is_file(),
                    f"Broken local link in {path.name}: {link}")
    print("PASS: Blank deployment template and local documentation links")

    tracked = subprocess.run(["git", "ls-files", "-z", "--cached"], cwd=ROOT,
                             capture_output=True, timeout=10)
    if tracked.returncode:
        print("SKIP: No Git index yet; tracked-file guard will run in GitHub Actions")
        return
    private_key = re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
    for name in tracked.stdout.decode().split("\0"):
        if not name:
            continue
        path = Path(name)
        require(not (path.name.startswith(".env") and path.name != ".env.example")
                and path.suffix not in {".pem", ".key", ".dump", ".sql", ".db"}
                and not ({"backups", "secrets", "data"} & set(path.parts))
                and path.parts[:2] != ("runner", "state"),
                f"Deployment data or credentials must not be tracked: {name}")
        local = ROOT / path
        if local.is_file():
            require(not private_key.search(local.read_bytes()),
                    f"Private key material found in tracked file: {name}")
    print("PASS: No tracked deployment files or private keys (basic guard, not a full secret scan)")


def runner_configuration():
    result = subprocess.run(
        ["docker", "compose", "--env-file", os.devnull,
         "-f", "runner/compose.yaml", "config", "--format", "json"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    require(result.returncode == 0, "Runner Compose validation failed: " + result.stderr)
    services = json.loads(result.stdout)["services"]
    require(set(services) == {"docker", "runner"}, "Unexpected runner services")
    for name, service in services.items():
        require(not service.get("ports"), f"Runner service {name} must not expose host ports")
        for mount in service.get("volumes", []):
            require(mount["type"] != "bind" or mount["target"] == "/data",
                    "Runner must not bind-mount the host Docker socket or host directories")
    require(services["runner"]["network_mode"] == "service:docker",
            "Runner cache requires the DinD network namespace")
    require(services["runner"]["user"] == "1000:1000"
            and not services["runner"].get("privileged", False),
            "Runner process must run without root privileges")
    require(int(services["docker"]["mem_limit"]) <= 5 * 1024**3,
            "DinD must leave memory for the Forgejo stack")
    print("PASS: Optional runner ports, Docker isolation, and resource bounds")


def main():
    configuration()
    runner_configuration()
    repository_files()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
