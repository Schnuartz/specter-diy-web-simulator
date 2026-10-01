#!/usr/bin/env python3
"""Resolve only identity supplied by the caller's GitHub event."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
COMMIT = re.compile(r"[a-f0-9]{40}\Z")


def resolve(env: dict[str, str]) -> dict:
    event = env["SOURCE_EVENT"]
    caller = env["GITHUB_REPOSITORY"]
    default_branch = env["SOURCE_DEFAULT_BRANCH"]
    base_repository = env["SOURCE_BASE_REPOSITORY"]
    base_branch = env["SOURCE_BASE_BRANCH"]
    repository = env["SOURCE_REPOSITORY"]
    commit = env["SOURCE_SHA"]
    branch = env["SOURCE_BRANCH"]
    number_text = env["SOURCE_PR_NUMBER"].strip()

    if event == "pull_request":
        if not re.fullmatch(r"[1-9][0-9]{0,6}", number_text):
            raise ValueError("Invalid pull request number")
        number = int(number_text)
        if base_repository.lower() != caller.lower() or base_branch != default_branch:
            raise ValueError("Pull request does not target this repository's default branch")
    elif event == "push":
        valid_push = (
            number_text == "0"
            and base_repository.lower() == caller.lower()
            and base_branch == default_branch
            and branch == default_branch
            and env["GITHUB_REF"] == f"refs/heads/{default_branch}"
            and repository.lower() == caller.lower()
        )
        if not valid_push:
            raise ValueError("Push is not for this repository's default branch")
        number = 0
    else:
        raise ValueError("Unsupported caller event")

    simulator_repository = env["SIMULATOR_REPOSITORY"]
    simulator_sha = env["SIMULATOR_SHA"]
    run_id_text = env["GITHUB_RUN_ID"]
    run_attempt_text = env["GITHUB_RUN_ATTEMPT"]
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id_text) or \
            not re.fullmatch(r"[1-9][0-9]{0,5}", run_attempt_text):
        raise ValueError("Invalid workflow run identity")
    if not REPOSITORY.fullmatch(repository) or not COMMIT.fullmatch(commit) or not branch:
        raise ValueError("Invalid source repository or commit identity")
    if simulator_repository != "cryptoadvance/specter-diy-web-simulator" or not COMMIT.fullmatch(simulator_sha):
        raise ValueError("Invalid reusable workflow identity")

    return {
        "event": event,
        "number": number,
        "branch": branch,
        "repository": repository,
        "commit": commit,
        "base_repository": base_repository,
        "base_branch": base_branch,
        "simulator_repository": simulator_repository,
        "simulator_commit": simulator_sha,
        "workflow_run_id": int(run_id_text),
        "workflow_run_attempt": int(run_attempt_text),
    }


def main() -> None:
    target = resolve(os.environ)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for key in ("repository", "commit", "number", "branch", "base_repository",
                    "base_branch", "simulator_repository", "simulator_commit",
                    "workflow_run_id", "workflow_run_attempt"):
            output.write(f"{key}={target[key]}\n")
    Path("target.json").write_text(json.dumps(target, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
