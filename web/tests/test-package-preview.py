#!/usr/bin/env python3
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from package_preview import package

SIMULATOR = "cryptoadvance/specter-diy-web-simulator"
SIMULATOR_SHA = "b" * 40
REPOSITORY = "alice/specter-diy"


class PackagePreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "-C", str(self.source), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.source), "config", "user.email", "test@example.invalid"], check=True)
        (self.source / "source.txt").write_text("source")
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.source), "commit", "-qm", "fixture"], check=True)
        self.source_sha = subprocess.run(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"],
            check=True, text=True, capture_output=True,
        ).stdout.strip()
        self.web = self.root / "web"
        self.build_path = f"builds/{REPOSITORY}/{self.source_sha}/"
        (self.web / "browser").mkdir(parents=True)
        (self.web / self.build_path).mkdir(parents=True)
        self.artifacts = {
            name: name.encode()
            for name in ("micropython.js", "micropython.wasm", "micropython.data")
        }
        records = {
            name: {"bytes": len(data), "sha256": sha256(data).hexdigest()}
            for name, data in self.artifacts.items()
        }
        artifact_set = sha256("".join(records[name]["sha256"] for name in sorted(records)).encode()).hexdigest()
        (self.web / "browser/current.json").write_text(json.dumps({
            "build": self.build_path, "version": artifact_set[:16],
        }))
        manifest = {
            "source": {
                "repository": REPOSITORY,
                "url": f"https://github.com/{REPOSITORY}",
                "commit": self.source_sha,
            },
            "simulator": {"repository": SIMULATOR, "commit": SIMULATOR_SHA},
            "artifacts": records,
            "artifact_set_sha256": artifact_set,
        }
        (self.web / self.build_path / "build-info.json").write_text(json.dumps(manifest))
        for name, data in self.artifacts.items():
            (self.web / self.build_path / name).write_bytes(data)

    def run_package(self, **overrides):
        args = {
            "web": self.web,
            "source": self.source,
            "output": self.root / "out",
            "source_repository": REPOSITORY,
            "source_sha": self.source_sha,
            "pr_number": 12,
            "simulator_repository": SIMULATOR,
            "simulator_sha": SIMULATOR_SHA,
        }
        args.update(overrides)
        return package(**args)

    def test_writes_small_provenance_with_each_payload_hash(self):
        result = self.run_package()
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["source_repository"], REPOSITORY)
        self.assertEqual(result["source_sha"], self.source_sha)
        self.assertEqual(result["pr_number"], 12)
        self.assertEqual(result["web_simulator_repository"], SIMULATOR)
        self.assertEqual(result["web_simulator_sha"], SIMULATOR_SHA)
        self.assertEqual(result["workflow_run_id"], 1)
        self.assertEqual(result["workflow_run_attempt"], 1)
        self.assertEqual(set(result["files"]), {
            "browser/current.json",
            self.build_path + "build-info.json",
            self.build_path + "micropython.js",
            self.build_path + "micropython.wasm",
            self.build_path + "micropython.data",
        })
        for name, record in result["files"].items():
            data = (self.root / "out" / name).read_bytes()
            self.assertEqual(record, {"bytes": len(data), "sha256": sha256(data).hexdigest()})

    def test_rejects_wrong_source_simulator_or_repository(self):
        for overrides in (
            {"source_sha": "c" * 40},
            {"source_repository": "alice/other-repo"},
            {"simulator_sha": "c" * 40},
            {"simulator_repository": "attacker/tools"},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self.run_package(**overrides)

    def test_rejects_manifest_hash_mismatch(self):
        (self.web / self.build_path / "micropython.wasm").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            self.run_package()

    def test_rejects_traversal_pointer(self):
        pointer = self.web / "browser/current.json"
        pointer.write_text(json.dumps({"build": "../outside/", "version": "bad"}))
        with self.assertRaisesRegex(ValueError, "pointer"):
            self.run_package()

    def test_rejects_symlinked_build_input(self):
        link = self.web / self.build_path / "micropython.js"
        link.unlink()
        outside = self.root / "outside.js"
        outside.write_bytes(b"outside")
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Symlink creation is not available")
        with self.assertRaisesRegex(ValueError, "Symlink|Unsafe or missing"):
            self.run_package()


if __name__ == "__main__":
    unittest.main()
