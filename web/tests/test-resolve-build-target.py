#!/usr/bin/env python3
"""Caller-derived source selection never follows moving branches."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from resolve_build_target import resolve

BASE = "cryptoadvance/specter-diy"
FORK = "alice/specter-diy"
SHA = "a" * 40
SIMULATOR = "cryptoadvance/specter-diy-web-simulator"
SIMULATOR_SHA = "b" * 40


class ResolveTests(unittest.TestCase):
    def env(self, event="pull_request"):
        return {
            "SOURCE_EVENT": event,
            "SOURCE_REPOSITORY": FORK if event == "pull_request" else BASE,
            "SOURCE_SHA": SHA,
            "SOURCE_PR_NUMBER": "19" if event == "pull_request" else "0",
            "SOURCE_BRANCH": "feature/new" if event == "pull_request" else "master",
            "SOURCE_BASE_REPOSITORY": BASE,
            "SOURCE_BASE_BRANCH": "master",
            "SOURCE_DEFAULT_BRANCH": "master",
            "GITHUB_REF": "refs/pull/19/merge" if event == "pull_request" else "refs/heads/master",
            "GITHUB_REPOSITORY": BASE,
            "SIMULATOR_REPOSITORY": SIMULATOR,
            "SIMULATOR_SHA": SIMULATOR_SHA,
            "GITHUB_RUN_ID": "101",
            "GITHUB_RUN_ATTEMPT": "2",
        }

    def test_pr_source_and_workflow_identity_come_from_caller(self):
        target = resolve(self.env())
        self.assertEqual(target["repository"], FORK)
        self.assertEqual(target["commit"], SHA)
        self.assertEqual(target["number"], 19)
        self.assertEqual(target["simulator_repository"], SIMULATOR)
        self.assertEqual(target["simulator_commit"], SIMULATOR_SHA)
        self.assertEqual(target["workflow_run_id"], 101)
        self.assertEqual(target["workflow_run_attempt"], 2)

    def test_default_branch_push_has_no_pr(self):
        target = resolve(self.env("push"))
        self.assertEqual(target["repository"], BASE)
        self.assertEqual(target["number"], 0)
        self.assertEqual(target["branch"], "master")

    def test_rejects_untrusted_or_malformed_targets(self):
        cases = (
            {"SOURCE_BASE_BRANCH": "other"},
            {"SOURCE_BASE_REPOSITORY": "attacker/elsewhere"},
            {"SOURCE_PR_NUMBER": "0"},
            {"SOURCE_SHA": "not-a-sha"},
            {"SOURCE_REPOSITORY": "../escape"},
            {"SIMULATOR_REPOSITORY": "attacker/tools"},
            {"SIMULATOR_SHA": "main"},
            {"GITHUB_RUN_ATTEMPT": "0"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                env = self.env()
                env.update(changes)
                with self.assertRaises(ValueError):
                    resolve(env)

    def test_push_must_be_from_callers_default_branch(self):
        for changes in (
            {"SOURCE_BRANCH": "feature"},
            {"GITHUB_REF": "refs/heads/feature"},
            {"SOURCE_REPOSITORY": FORK},
        ):
            with self.subTest(changes=changes):
                env = self.env("push")
                env.update(changes)
                with self.assertRaises(ValueError):
                    resolve(env)


if __name__ == "__main__":
    unittest.main()
