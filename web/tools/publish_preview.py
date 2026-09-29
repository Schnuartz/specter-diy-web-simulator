#!/usr/bin/env python3
"""Trusted Pages publisher. Never executes files from a PR build artifact."""
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "browser"))
from verify_build import verify  # type: ignore[import-not-found]
from replace_glue import replace_glue  # type: ignore[import-not-found]

MARKER = "<!-- specter-pr-build-comment -->"
MANUAL_RUN = re.compile(r"Manual PR[ \t]+([1-9][0-9]{0,6})[ \t]+([a-f0-9]{7,40})[ \t]*")
TRUSTED_WEB = Path(__file__).resolve().parents[1]


def read_json_file(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError(f"Invalid artifact metadata: {path.name}")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Invalid artifact metadata: {path.name}")
    return data


def api(method: str, path: str, body=None):
    base = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}"
    data = None if body is None else json.dumps(body).encode()
    request = Request(base + path, data=data, method=method, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        **({"Content-Type": "application/json"} if data is not None else {}),
    })
    with urlopen(request, timeout=30) as response:
        content = response.read()
    return json.loads(content) if content else None


def find_current_pr(run: dict) -> dict | None:
    """Identify a current PR using GitHub metadata, never a build artifact."""
    associated = run.get("pull_requests") or []
    event_heads = {}
    if associated:
        numbers = {item.get("number") for item in associated}
        if any(type(number) is not int or not 0 < number < 1_000_000 for number in numbers):
            return None
        candidates = [api("GET", f"/pulls/{number}") for number in sorted(numbers)]
        event_heads = {item["number"]: (item.get("head") or {}).get("sha")
                       for item in associated}
    else:
        # workflow_run.pull_requests is empty for some fork PRs. GitHub's
        # head filter narrows the API lookup; the SHA and full repository are
        # checked below before any preview or comment can be changed.
        head_repo = run.get("head_repository") or {}
        full_name = head_repo.get("full_name", "")
        branch = run.get("head_branch")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) or \
                not isinstance(branch, str) or not branch:
            return None
        head_filter = quote(f"{full_name.split('/')[0]}:{branch}", safe="")
        candidates = []
        for page in range(1, 11):
            batch = api("GET", f"/pulls?state=open&head={head_filter}&per_page=100&page={page}")
            candidates.extend(batch)
            if len(batch) < 100:
                break
    matches = []
    for pr in candidates:
        head = pr.get("head") or {}
        repo = head.get("repo") or {}
        event_head = event_heads.get(pr.get("number"))
        event_head_present = isinstance(event_head, str) and \
            bool(re.fullmatch(r"[a-f0-9]{40}", event_head))
        if event_head_present and event_head != head.get("sha"):
            continue
        if pr.get("state") != "open" or not (event_head_present or
                run.get("head_sha") in (head.get("sha"), pr.get("merge_commit_sha"))):
            continue
        if not associated and (repo.get("full_name", "").lower() != full_name.lower() or
                head.get("ref") != branch or run.get("head_sha") != head.get("sha")):
            continue
        matches.append(pr)
    return matches[0] if len(matches) == 1 else None


def find_current_manual_pr(run: dict, repository: str, default_branch: str) -> dict | None:
    """A dispatch run names its PR and SHA before any untrusted job executes."""
    title = run.get("display_title")
    match = MANUAL_RUN.fullmatch(title) if isinstance(title, str) else None
    head_repo = run.get("head_repository") or {}
    run_sha = run.get("head_sha")
    if not match or run.get("head_branch") != default_branch or \
            head_repo.get("full_name", "").lower() != repository.lower() or \
            not isinstance(run_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", run_sha):
        return None
    number, sha = int(match[1]), match[2]
    pr = api("GET", f"/pulls/{number}")
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    current_sha = head.get("sha")
    if pr.get("state") != "open" or not isinstance(current_sha, str) or \
            not re.fullmatch(r"[a-f0-9]{40}", current_sha) or \
            not current_sha.startswith(sha) or \
            (base.get("repo") or {}).get("full_name", "").lower() != repository.lower() or \
            base.get("ref") != default_branch:
        return None
    return pr


def find_current_target_pr(target: dict, repository: str, default_branch: str) -> dict | None:
    """Bind the trusted Build target artifact to the current PR head."""
    number = target.get("number")
    sha = target.get("commit")
    source_repository = target.get("repository")
    branch = target.get("branch")
    if target.get("event") != "workflow_run" or type(number) is not int or \
            not 0 < number < 1_000_000 or not isinstance(sha, str) or \
            not re.fullmatch(r"[a-f0-9]{40}", sha) or \
            not isinstance(source_repository, str) or not isinstance(branch, str):
        return None
    pr = api("GET", f"/pulls/{number}")
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    if pr.get("number") != number or pr.get("state") != "open" or head.get("sha") != sha or \
            (head.get("repo") or {}).get("full_name", "").lower() != source_repository.lower() or \
            head.get("ref") != branch or \
            (base.get("repo") or {}).get("full_name", "").lower() != repository.lower() or \
            base.get("ref") != default_branch:
        return None
    return pr


def read_source(directory: Path, kind: str, sha: str, repo: str) -> dict:
    source = read_json_file(directory / "source.json")
    if source.get("kind") != kind or source.get("commit") != sha or \
            source.get("repository", "").lower() != repo.lower():
        raise ValueError(f"{kind} artifact belongs to a different source commit")
    return source


def validate_artifact_tree(root: Path, build_path: str):
    if not root.is_dir():
        raise ValueError("Browser artifact directory missing")
    allowed = {"browser/current.json"} | {
        build_path + name for name in
        ("build-info.json", "micropython.js", "micropython.wasm", "micropython.data")
    }
    for path in root.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe artifact path")
        relative = path.relative_to(root).as_posix()
        if path.is_file() and relative not in allowed:
            raise ValueError(f"Unexpected browser artifact: {relative}")
    if not all((root / name).is_file() for name in allowed):
        raise ValueError("Browser artifact is incomplete")


def validate_bundles(browser: Path, firmware: Path, sha: str, repo: str) -> dict:
    read_source(browser, "browser", sha, repo)
    fw = read_source(firmware, "firmware", sha, repo)
    for name in ("bin/specter-diy.bin", "bin/specter-diy.hex"):
        path = firmware / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing firmware artifact: {name}")
        from hashlib import sha256
        if sha256(path.read_bytes()).hexdigest() != fw["sha256"].get(name):
            raise ValueError(f"Firmware hash mismatch: {name}")
    web = browser / "web"
    manifest = verify(web, sha, repo)
    pointer = read_json_file(web / "browser/current.json")
    validate_artifact_tree(web, pointer["build"])
    if not manifest.get("experimental"):
        raise ValueError("Development build warning missing from manifest")
    if "NEVER ENTER A REAL SEED PHRASE" not in (TRUSTED_WEB / "index.html").read_text():
        raise ValueError("Development build warning missing from page")
    for name in ("browser/site.js", "browser/runtime-worker.js"):
        if not (TRUSTED_WEB / name).is_file():
            raise ValueError(f"Missing browser shell: {name}")
    return manifest


def publish_files(web: Path, pages: Path, number: int | None, sha: str):
    """Publish only firmware data from the build artifact; supply our own shell."""
    pages = pages.resolve()
    target = pages / "pr" / str(number) if number else pages
    if not target.resolve().is_relative_to(pages) or pages == target and number:
        raise ValueError("Invalid preview destination")
    if number and target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    if number is None:
        # Replace stale stable-site shell files without disturbing PR previews.
        for name in ("index.html", "assets", "browser", "builds"):
            old = target / name
            if old.is_symlink():
                raise ValueError(f"Unsafe existing Pages path: {name}")
            if old.is_dir():
                shutil.rmtree(old)
            elif old.exists():
                old.unlink()
    for name in ("index.html", "assets", "browser"):
        source = TRUSTED_WEB / name
        destination = target / name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)
    shutil.copy2(web / "browser/current.json", target / "browser/current.json")
    shutil.copytree(web / "builds", target / "builds", dirs_exist_ok=True)
    index = target / "index.html"
    contents = index.read_text().replace('./browser/site.js"', f'./browser/site.js?v={sha[:12]}"')
    index.write_text(contents)
    (pages / ".nojekyll").touch()


def artifact_id(run_id: int, name: str) -> int:
    artifacts = api("GET", f"/actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    found = [item["id"] for item in artifacts if item["name"] == name and not item["expired"]]
    if len(found) != 1:
        raise ValueError(f"Expected one unexpired {name} artifact")
    return found[0]


def comment(state: dict):
    number = state.get("number")
    if not number:
        return
    run_url = state["run_url"]
    sha = state["sha"]
    if state["published"]:
        repo = os.environ["GITHUB_REPOSITORY"]
        pages_owner = repo.split("/")[0].lower()
        pages_url = f"https://{pages_owner}.github.io/{repo.split('/')[1]}/pr/{number}/"
        firmware_url = f"{run_url}/artifacts/{artifact_id(state['run_id'], 'firmware-binaries')}"
        simulator = state["simulator"]
        source = state["repo"]
        source_link = f"https://github.com/{source}/commit/{sha}"
        simulator_link = (f"https://github.com/{simulator['repository']}/commit/"
                          f"{simulator['commit']}")
        body = (f"{MARKER}\n🧪 **Specter PR Build** · `{sha[:7]}` ✅\n\n"
                "<details>\n<summary>Build provenance</summary>\n\n"
                f"**Specter source:** [{source}@{sha[:12]}]({source_link})\n"
                f"**Simulator tooling:** [{simulator['repository']}@{simulator['commit'][:12]}]({simulator_link})\n"
                f"🔧 [Build workflow and logs]({run_url})\n"
                "</details>\n\n"
                f"🖥️ <a href=\"{pages_url}\" target=\"_blank\" rel=\"noopener noreferrer\">Open browser simulator</a>\n\n"
                f"⬇️ [Download firmware from the same commit]({firmware_url})\n\n"
                "⚠️ **Experimental development build.** Never use real funds or enter a real seed phrase. "
                "Use dedicated test hardware for firmware builds.")
    else:
        body = (f"{MARKER}\n🧪 **Specter PR Build** · `{sha[:7]}` ❌\n\n"
                "The current PR commit has no published browser preview or matching firmware build. "
                f"[Inspect build logs]({run_url}).\n\n"
                "⚠️ Previous previews must not be treated as this commit.")
    existing = []
    for page in range(1, 11):
        batch = api("GET", f"/issues/{number}/comments?per_page=100&page={page}")
        existing.extend(batch)
        if len(batch) < 100:
            break
    for entry in existing:
        if MARKER in entry.get("body", "") and entry.get("user", {}).get("login") == "github-actions[bot]":
            api("DELETE", f"/issues/comments/{entry['id']}")
    api("POST", f"/issues/{number}/comments", {"body": body})


def prepare(args):
    def skip(reason: str):
        state = {"skip": True, "reason": reason}
        Path(args.state).write_text(json.dumps(state, indent=2) + "\n")
        print(reason)
        return state

    event = json.loads(Path(args.event).read_text())
    run = event["workflow_run"]
    # GitHub sets workflow_run.name to the dynamic run-name, e.g. "PR 17" or
    # "Manual PR 17 abc1234". Its workflow file path is the stable identity.
    workflow_path = str(run.get("path", "")).split("@", 1)[0]
    if workflow_path != ".github/workflows/build.yml" or \
            run["event"] not in ("workflow_run", "push", "workflow_dispatch"):
        raise ValueError("Unrecognized workflow run")
    repository = os.environ["GITHUB_REPOSITORY"]
    browser = Path(args.browser)
    firmware = Path(args.firmware)
    if run["event"] in ("workflow_run", "workflow_dispatch"):
        trusted_target = None
        if run["event"] == "workflow_run":
            try:
                trusted_target = read_json_file(Path(args.target))
            except (OSError, ValueError, json.JSONDecodeError):
                return skip("Trusted Build target missing; cannot identify a PR safely")
        pr = (find_current_target_pr(trusted_target, repository, event["repository"]["default_branch"])
              if run["event"] == "workflow_run"
              else find_current_manual_pr(run, repository,
                                          event["repository"]["default_branch"]))
        if not pr:
            return skip("PR head advanced or PR closed; skip stale workflow run")
        sha, repo, number = pr["head"]["sha"], pr["head"]["repo"]["full_name"], pr["number"]
    else:
        if run["head_branch"] not in ("master", "main"):
            return skip("Default-branch run is no longer publishable")
        sha, repo, number = run["head_sha"], repository, None
    state = {"skip": False, "number": number, "sha": sha, "repo": repo,
             "run_id": run["id"], "run_url": run["html_url"], "published": False}
    pages = Path(args.pages)
    if run["conclusion"] == "success":
        try:
            if not args.target:
                raise ValueError("Workflow target artifact missing")
            target = read_json_file(Path(args.target))
            if target.get("event") != run["event"] or target.get("commit") != sha or \
                    not isinstance(target.get("repository"), str) or \
                    target["repository"].lower() != repo.lower() or \
                    target.get("number") != (number or 0) or \
                    (number and target.get("branch") != pr["head"]["ref"]) or \
                    not isinstance(target.get("simulator_repository"), str) or \
                    not isinstance(target.get("simulator_commit"), str):
                raise ValueError("Workflow target does not match current run")
            replace_glue(browser / "web", Path(args.runtime))
            manifest = validate_bundles(browser, firmware, sha, repo)
            simulator = manifest["simulator"]
            if simulator["repository"].lower() != target["simulator_repository"].lower() or \
                    simulator["commit"] != target["simulator_commit"]:
                raise ValueError("Browser simulator tooling does not match workflow target")
        except Exception as error:
            # Artifact content is untrusted data. Any missing or malformed
            # artifact makes this current PR build unpublishable.
            state["reason"] = f"Build artifacts unavailable or invalid: {error}"
            print(state["reason"])
        else:
            state["simulator"] = simulator
            publish_files(browser / "web", pages, number, sha)
            state["published"] = True
    if number and not state["published"]:
        target = pages.resolve() / "pr" / str(number)
        if target.exists() and target.is_relative_to(pages.resolve()):
            shutil.rmtree(target)
    Path(args.state).write_text(json.dumps(state, indent=2) + "\n")
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "comment"))
    parser.add_argument("--event")
    parser.add_argument("--target")
    parser.add_argument("--browser")
    parser.add_argument("--firmware")
    parser.add_argument("--runtime")
    parser.add_argument("--pages")
    parser.add_argument("--state", required=True)
    args = parser.parse_args()
    if args.phase == "prepare":
        print(prepare(args))
    else:
        state = json.loads(Path(args.state).read_text())
        if not state.get("skip"):
            comment(state)


if __name__ == "__main__":
    main()
