from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILD = (ROOT / ".github/workflows/build-preview.yml").read_text()
CHECKS = (ROOT / ".github/workflows/checks.yml").read_text()
VH_SHA = "3cf3ecd58a97da0f2cc4b7586ca33abf02f68372"


class WorkflowContractTests(unittest.TestCase):
    def test_reusable_workflow_uses_caller_identity_and_no_inputs_or_secrets(self):
        self.assertRegex(BUILD, r"(?m)^on:\n  workflow_call:")
        self.assertIn("job.workflow_repository", BUILD)
        self.assertIn("job.workflow_sha", BUILD)
        self.assertIn("github.event.pull_request.head.sha", BUILD)
        self.assertNotRegex(BUILD, r"(?m)^\s+secrets:")
        self.assertNotRegex(BUILD, r"(?m)^\s+pages:\s+write")
        self.assertNotRegex(BUILD, r"(?m)^\s+issues:\s+write")
        self.assertNotRegex(BUILD, r"(?m)^\s+contents:\s+write")
        self.assertIn("permissions:\n  contents: read", BUILD)

    def test_all_external_actions_use_full_commit_shas(self):
        actions = re.findall(r"(?m)^[ \t]*-[ \t]*uses:[ \t]*[^@\s]+@([^\s]+)[ \t]*$", BUILD + "\n" + CHECKS)
        self.assertTrue(actions)
        self.assertTrue(all(re.fullmatch(r"[a-f0-9]{40}", ref) for ref in actions), actions)

    def test_virtual_host_is_immutable_and_emulator_tests_are_local(self):
        self.assertIn(f"ref: {VH_SHA}", BUILD)
        self.assertNotIn("git clone --depth 1 https://github.com/cryptoadvance/specter-virtual-host.git", BUILD)
        self.assertIn("test-network-policy.mjs", BUILD)
        self.assertIn("test-usb-transport.mjs", BUILD)
        self.assertIn("test-usb-vcp.py", BUILD)

    def test_versions_and_provenance_contract_are_explicit(self):
        for expected in ("3.1.74", "22.20.0", "3.11.9", "1.25.5",
                         "schema_version", "source_repository", "source_sha",
                         "web_simulator_repository", "web_simulator_sha", "pr_number",
                         "workflow_run_id", "workflow_run_attempt"):
            if expected in ("schema_version", "source_repository", "source_sha",
                            "web_simulator_repository", "web_simulator_sha", "pr_number",
                            "workflow_run_id", "workflow_run_attempt"):
                source = (ROOT / "web/tools/package_preview.py").read_text()
                self.assertIn(expected, source)
            else:
                self.assertIn(expected, BUILD)


if __name__ == "__main__":
    unittest.main()
