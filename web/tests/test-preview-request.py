#!/usr/bin/env python3
"""Request validation must bind dispatch metadata to GitHub's live PR."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_preview_request import parse_request, validate_request


BASE = "cryptoadvance/specter-diy"
SERVICE = "cryptoadvance/specter-diy-web-simulator"
HEAD = "bob/specter-diy"
SHA = "a" * 40
UPDATED = "2026-09-30T12:00:00Z"


def payload(action="build"):
    return {
        "request_id": f"specter-pr-19-{SHA}-101-1",
        "action": action,
        "base_repository": BASE,
        "pr_number": "19",
        "head_repository": HEAD,
        "head_sha": SHA,
        "head_ref": "feature/browser-preview",
        "source_updated_at": UPDATED,
    }


def pull(state="open", repository=HEAD, sha=SHA, updated=UPDATED, number=19, base=BASE):
    return {
        "number": number,
        "state": state,
        "updated_at": updated,
        "head": {
            "sha": sha,
            "ref": "feature/browser-preview",
            "repo": {"full_name": repository} if repository else None,
        },
        "base": {"repo": {"full_name": base}, "ref": "master"},
    }


class PreviewRequestTests(unittest.TestCase):
    def test_contributor_fork_request_resolves_against_paired_base(self):
        result = validate_request(payload(), SERVICE, "token", lambda *_: pull())
        self.assertEqual(result["base_repository"], BASE)
        self.assertEqual(result["head_repository"], HEAD)
        self.assertEqual(result["head_sha"], SHA)
        self.assertEqual(result["pr_number"], 19)

    def test_service_owner_determines_base_repository(self):
        bad = payload()
        bad["base_repository"] = "bob/specter-diy"
        with self.assertRaisesRegex(ValueError, "base_repository must be cryptoadvance/specter-diy"):
            parse_request(bad, SERVICE)

    def test_repository_override_keeps_the_paired_owner_rule(self):
        result = parse_request(payload(), "cryptoadvance/custom-preview-service")
        self.assertEqual(result["base_repository"], BASE)

    def test_build_rejects_wrong_live_base_head_sha_repo_ref_or_closed_pr(self):
        cases = [
            (pull(base="evil/specter-diy"), "another base repository"),
            (pull(sha="c" * 40), "head SHA"),
            (pull(repository="mallory/specter-diy"), "head repository"),
            (pull(state="closed"), "open PR"),
        ]
        for live, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_request(payload(), SERVICE, "token", lambda *_: live)

    def test_close_request_accepts_deleted_head_repository_but_requires_closed_pr(self):
        closed = payload("delete")
        closed["head_repository"] = ""
        closed["head_ref"] = ""
        result = validate_request(closed, SERVICE, "token",
                                  lambda *_: pull(state="closed", repository=""))
        self.assertEqual(result["action"], "delete")
        with self.assertRaisesRegex(ValueError, "closed PR"):
            validate_request(closed, SERVICE, "token", lambda *_: pull(state="open"))

    def test_metadata_only_update_does_not_invalidate_matching_source_sha(self):
        result = validate_request(payload(), SERVICE, "token",
                                  lambda *_: pull(updated="2026-10-01T12:00:00Z"))
        self.assertEqual(result["head_sha"], SHA)

    def test_rejects_future_timestamp_even_when_head_sha_is_current(self):
        future = payload()
        future["source_updated_at"] = "2099-10-01T12:00:00Z"
        future["request_id"] = f"specter-pr-19-{SHA}-101-1"
        with self.assertRaisesRegex(ValueError, "ahead of current PR metadata"):
            validate_request(future, SERVICE, "token", lambda *_: pull())

    def test_rejects_request_identity_sha_and_ref_tampering(self):
        cases = []
        bad = payload()
        bad["request_id"] = f"specter-pr-19-{'b' * 40}-101-1"
        cases.append((bad, "request_id"))
        bad = payload()
        bad["head_sha"] = "a" * 39
        cases.append((bad, "full 40-character"))
        bad = payload()
        bad["head_ref"] = "../attacker"
        cases.append((bad, "valid head_ref"))
        bad = payload()
        bad["source_updated_at"] = "2026-09-30T12:00:00"
        cases.append((bad, "include a timezone"))
        for values, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    parse_request(values, SERVICE)

    def test_rejects_non_paired_service_repository(self):
        with self.assertRaisesRegex(ValueError, "base_repository must be bob/specter-diy"):
            parse_request(payload(), "bob/alternate-web-simulator")


if __name__ == "__main__":
    unittest.main()
