#!/usr/bin/env python3
"""Stage the small, hashed browser payload consumed by Specter's publisher."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
import json
import os
import re
import shutil
import subprocess
import sys

REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
COMMIT = re.compile(r"[a-f0-9]{40}\Z")
ARTIFACTS = ("build-info.json", "micropython.js", "micropython.wasm", "micropython.data")
MAX_BUILD_INFO_BYTES = 1_000_000
MAX_PAYLOAD_BYTES = 300_000_000


def regular_file(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or "\\" in relative or any(part in ("", ".", "..") for part in posix.parts):
        raise ValueError(f"Unsafe build path: {relative}")
    path = root
    for part in posix.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Symlink in browser build path: {relative}")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Unsafe or missing build file: {relative}")
    return path


def package(web: Path, source: Path, output: Path, source_repository: str, source_sha: str,
            pr_number: int, simulator_repository: str, simulator_sha: str,
            run_id: int = 1, run_attempt: int = 1) -> dict:
    if web.is_symlink() or source.is_symlink() or output.is_symlink():
        raise ValueError("Unsafe browser build root")
    web, source = web.resolve(), source.resolve()
    actual_source_sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True, text=True, capture_output=True,
    ).stdout.strip()
    if actual_source_sha != source_sha or not COMMIT.fullmatch(source_sha):
        raise ValueError("Specter checkout does not match the resolved source SHA")
    if not REPOSITORY.fullmatch(source_repository) or any(part in (".", "..") for part in source_repository.split("/")):
        raise ValueError("Invalid Specter repository identity")
    if type(pr_number) is not int or not 0 <= pr_number <= 999999:
        raise ValueError("Invalid PR number")
    if type(run_id) is not int or run_id <= 0 or type(run_attempt) is not int or run_attempt <= 0:
        raise ValueError("Invalid workflow run identity")
    if simulator_repository != "cryptoadvance/specter-diy-web-simulator" or not COMMIT.fullmatch(simulator_sha):
        raise ValueError("Invalid Web Simulator workflow identity")

    pointer_path = regular_file(web, "browser/current.json")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    build_path = pointer.get("build")
    expected_path = f"builds/{source_repository}/{source_sha}/"
    if build_path != expected_path:
        raise ValueError("Browser build pointer does not match source identity")
    if not re.fullmatch(r"builds/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[a-f0-9]{40}/", build_path):
        raise ValueError("Invalid browser build pointer")

    manifest_file = regular_file(web, build_path + "build-info.json")
    if manifest_file.stat().st_size > MAX_BUILD_INFO_BYTES:
        raise ValueError("Build manifest is too large")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    source_record = manifest.get("source", {})
    simulator_record = manifest.get("simulator", {})
    if source_record.get("repository", "").lower() != source_repository.lower() or \
            source_record.get("commit") != source_sha:
        raise ValueError("Build manifest does not match Specter source")
    if simulator_record.get("repository", "").lower() != simulator_repository.lower() or \
            simulator_record.get("commit") != simulator_sha:
        raise ValueError("Build manifest does not match Web Simulator workflow")
    records = manifest.get("artifacts")
    if not isinstance(records, dict) or set(records) != set(ARTIFACTS[1:]):
        raise ValueError("Unexpected WebAssembly artifact set")
    artifact_set = sha256("".join(records[name].get("sha256", "")
                                   for name in sorted(records)).encode()).hexdigest()
    if manifest.get("artifact_set_sha256") != artifact_set or pointer.get("version") != artifact_set[:16]:
        raise ValueError("Browser build pointer or artifact-set hash does not match manifest")

    # Reject unsafe filesystem entries before copying any build output. Only
    # the selected build's four files and current pointer enter the artifact.
    for path in (web / "browser", web / "builds"):
        if path.is_symlink() or not path.resolve().is_relative_to(web):
            raise ValueError("Unsafe browser build directory")

    output = output.resolve()
    if output.exists() or output.is_symlink():
        raise ValueError("Preview output directory already exists")
    build_output = PurePosixPath(build_path)
    (output / build_output).mkdir(parents=True)
    (output / "browser").mkdir()
    files: dict[str, dict[str, object]] = {}
    for relative in ("browser/current.json", *(build_path + name for name in ARTIFACTS)):
        src = regular_file(web, relative)
        if src.stat().st_size > (MAX_BUILD_INFO_BYTES if relative.endswith("build-info.json") else MAX_PAYLOAD_BYTES):
            raise ValueError(f"Browser build file is too large: {relative}")
        dst = output / PurePosixPath(relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        data = dst.read_bytes()
        files[relative] = {"bytes": len(data), "sha256": sha256(data).hexdigest()}
        if relative.startswith(build_path) and relative.rsplit("/", 1)[-1] != "build-info.json":
            record = records[relative.rsplit("/", 1)[-1]]
            if type(record.get("bytes")) is not int or record.get("bytes") != len(data) or \
                    not isinstance(record.get("sha256"), str) or \
                    record.get("sha256") != files[relative]["sha256"]:
                raise ValueError(f"Build artifact hash does not match manifest: {relative}")

    provenance = {
        "schema_version": 1,
        "source_repository": source_repository,
        "source_sha": source_sha,
        "pr_number": pr_number,
        "web_simulator_repository": simulator_repository,
        "web_simulator_sha": simulator_sha,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "files": files,
    }
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


if __name__ == "__main__":
    if len(sys.argv) != 9:
        raise SystemExit("usage: package_preview.py WEB_ROOT SOURCE_CHECKOUT OUTPUT SOURCE_REPOSITORY SOURCE_SHA PR_NUMBER SIMULATOR_REPOSITORY SIMULATOR_SHA")
    result = package(
        Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5],
        int(sys.argv[6]), sys.argv[7], sys.argv[8],
        int(os.environ["GITHUB_RUN_ID"]), int(os.environ["GITHUB_RUN_ATTEMPT"]),
    )
    print(f"Packaged {len(result['files'])} files for {result['source_repository']}@{result['source_sha']}")
