#!/usr/bin/env python3
"""Static check for the service workflow's trust and ownership boundaries."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/preview.yml").read_text(encoding="utf-8")


def job(name, next_name=None):
    start = WORKFLOW.index(f"  {name}:\n")
    if next_name:
        end = WORKFLOW.index(f"  {next_name}:\n", start + 1)
        return WORKFLOW[start:end]
    return WORKFLOW[start:]


class PreviewWorkflowContractTests(unittest.TestCase):
    def test_remote_service_dispatches_then_validates_live_pr(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotIn("repository_dispatch:", WORKFLOW)
        self.assertIn("python3 web/tools/validate_preview_request.py", WORKFLOW)
        self.assertIn("DEFAULT_BRANCH:", WORKFLOW)
        for field in ("request_id", "base_repository", "pr_number", "head_repository",
                      "head_sha", "head_ref", "source_updated_at"):
            self.assertIn(f"      {field}:", WORKFLOW)

    def test_untrusted_job_has_read_only_permissions_and_no_secrets(self):
        build = job("build", "finalize")
        self.assertIn("permissions:\n      contents: read", build)
        self.assertNotIn("contents: write", build)
        self.assertNotIn("pages: write", build)
        self.assertNotIn("id-token: write", build)
        self.assertNotIn("secrets.", build)
        self.assertIn("persist-credentials: false", build)
        self.assertIn("ref: ${{ needs.validate.outputs.head_sha }}", build)
        self.assertIn("nix develop -c make disco", build)
        self.assertIn("build-browser.sh", build)
        self.assertIn("go test ./...", build)

    def test_only_always_finalizer_has_write_permissions_and_status_publisher(self):
        finalize = job("finalize")
        self.assertIn("always()", finalize)
        self.assertIn("contents: write", finalize)
        self.assertIn("pages: write", finalize)
        self.assertIn("id-token: write", finalize)
        self.assertIn("python3 simulator/web/tools/publish_preview.py", finalize)
        self.assertIn("actions/deploy-pages@", finalize)
        self.assertIn("preview-publish-${{ github.repository }}", finalize)

    def test_actions_are_immutable_and_virtual_host_pin_is_consistent(self):
        uses = re.findall(r"uses:\s+[^\s@]+@([^\s#]+)", WORKFLOW)
        self.assertTrue(uses)
        self.assertTrue(all(re.fullmatch(r"[a-f0-9]{40}", value) for value in uses), uses)
        pin = (ROOT / ".preview-config/virtual-host-commit").read_text().strip()
        self.assertEqual(pin, "3cf3ecd58a97da0f2cc4b7586ca33abf02f68372")
        self.assertIn(f"ref: {pin}", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
