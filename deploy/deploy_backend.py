#!/usr/bin/env python3
"""Pull main, test an isolated release, and switch the existing systemd API."""

import argparse
import fcntl
import grp
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import urlopen


REPOSITORY_URL = "https://github.com/zhchoice123/01tts.git"
SERVICE = "01tts-python-api.service"
BASE = Path("/opt/01tts")
DROP_IN = Path(f"/etc/systemd/system/{SERVICE}.d/20-git-release.conf")
HEALTH_URL = "http://127.0.0.1:8080/health"


def run(*command, cwd=None, capture=False):
    return subprocess.run(
        command, cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
    ).stdout


def write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(0o644)
    temporary.replace(path)


def read_override():
    return DROP_IN.read_text(encoding="utf-8") if DROP_IN.exists() else None


def restore_override(content):
    if content is None:
        DROP_IN.unlink(missing_ok=True)
    else:
        write_atomic(DROP_IN, content)


def restart_and_check():
    run("systemctl", "daemon-reload")
    run("systemctl", "restart", SERVICE)
    for _ in range(30):
        try:
            run("systemctl", "is-active", "--quiet", SERVICE)
            with urlopen(HEALTH_URL, timeout=2) as response:
                if json.load(response).get("status") == "UP":
                    return
        except (OSError, ValueError, subprocess.CalledProcessError):
            pass
        time.sleep(1)
    raise RuntimeError("API did not become healthy after restart")


def prepare_release():
    repository = BASE / "repository"
    if not repository.exists():
        run("git", "clone", "--branch", "main", "--single-branch",
            REPOSITORY_URL, str(repository))
    if run("git", "remote", "get-url", "origin", cwd=repository, capture=True).strip() != REPOSITORY_URL:
        raise RuntimeError("Unexpected origin URL; refusing deployment")
    if run("git", "status", "--porcelain", cwd=repository, capture=True).strip():
        raise RuntimeError("Server repository contains local edits; refusing deployment")
    if run("git", "branch", "--show-current", cwd=repository, capture=True).strip() != "main":
        raise RuntimeError("Server repository must be on main")
    run("git", "fetch", "origin", "main", cwd=repository)
    run("git", "merge", "--ff-only", "origin/main", cwd=repository)
    revision = run("git", "rev-parse", "HEAD", cwd=repository, capture=True).strip()
    release = BASE / "releases" / revision
    release.parent.mkdir(parents=True, exist_ok=True)
    if not release.exists():
        run("git", "worktree", "add", "--detach", str(release), revision, cwd=repository)
    if run("git", "rev-parse", "HEAD", cwd=release, capture=True).strip() != revision:
        raise RuntimeError("Release commit does not match fetched main")
    if run("git", "status", "--porcelain", cwd=release, capture=True).strip():
        raise RuntimeError("Release contains edits; refusing deployment")

    # Copy only the original ignored configuration, never its credentials into Git.
    shared_config = BASE / "settings" / "config.yaml"
    if not shared_config.exists():
        shared_config.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / "01tts-worker" / "config.yaml", shared_config)
        shared_config.chmod(0o640)
        os.chown(shared_config, 0, grp.getgrnam("01tts").gr_gid)
    config = release / "01tts-worker" / "config.yaml"
    if config.is_symlink():
        if config.resolve() != shared_config.resolve():
            raise RuntimeError("Release configuration points to an unexpected location")
    elif config.exists():
        raise RuntimeError("Unexpected release config.yaml; refusing to replace it")
    else:
        config.symlink_to(shared_config)

    # Each release gets its own dependencies, so rollback also restores the runtime.
    environment = BASE / "release-venvs" / revision
    if not (environment / "bin" / "python").exists():
        run(str(BASE / "venv" / "bin" / "python"), "-m", "venv", str(environment))
    python = str(environment / "bin" / "python")
    run(python, "-m", "pip", "install", "-r", str(release / "01tts-worker" / "requirements.txt"))
    run(python, "-m", "unittest", "discover", "-s", "tests", "-v", cwd=release / "01tts-worker")
    return revision, release, environment


def activate(revision, release, environment):
    previous = read_override()
    state = BASE / "deployment-state.json"
    old_state = json.loads(state.read_text()) if state.exists() else {}
    override = (
        "[Service]\n"
        f"WorkingDirectory={release}/01tts-worker\n"
        "ExecStart=\n"
        f"ExecStart={environment}/bin/uvicorn api:app --host 127.0.0.1 --port 8080 --workers 1\n"
    )
    try:
        write_atomic(DROP_IN, override)
        restart_and_check()
        write_atomic(state, json.dumps({
            "current": revision,
            "previous": old_state.get("current", "legacy-scp"),
            "previous_override": previous,
        }, indent=2) + "\n")
    except Exception:
        restore_override(previous)
        restart_and_check()
        raise
    print(f"Deployed main at {revision}; API health UP")


def rollback():
    state = BASE / "deployment-state.json"
    record = json.loads(state.read_text())
    if "previous_override" not in record:
        raise RuntimeError("No recorded rollback target")
    current_override = read_override()
    try:
        restore_override(record["previous_override"])
        restart_and_check()
    except Exception:
        restore_override(current_override)
        restart_and_check()
        raise
    write_atomic(state, json.dumps({
        "current": record["previous"],
        "previous": record["current"],
        "previous_override": current_override,
    }, indent=2) + "\n")
    print(f"Rolled back to {record['previous']}; API health UP")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "deploy", "rollback"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run on the cloud server as root (or with sudo)")
    BASE.mkdir(parents=True, exist_ok=True)
    with (BASE / "deployment.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "rollback":
            rollback()
        else:
            revision, release, environment = prepare_release()
            if args.action == "deploy":
                if read_override() is not None and (BASE / "deployment-state.json").exists():
                    current = json.loads((BASE / "deployment-state.json").read_text())["current"]
                    if current == revision:
                        print(f"Already deployed {revision}; no restart needed")
                        return
                activate(revision, release, environment)
            else:
                print(f"Checked main at {revision}; service unchanged")


if __name__ == "__main__":
    main()
