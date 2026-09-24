"""Behavior and refusal tests using the real sample as the regression fixture."""
import tempfile
import unittest
import os
import subprocess
import sys
from pathlib import Path

from transform import (DEFAULT_BASELINE, DEFAULT_SOURCE, ROOT, POLICY, Unsupported,
                       condition, dump_yaml, enhance, load_yaml, normalize_condition, read, main)
from compare import lint, make_report


class TransformationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = read(DEFAULT_BASELINE)
        cls.source = read(DEFAULT_SOURCE)
        cls.policy = POLICY
        cls.output, cls.changes = enhance(cls.raw, cls.source, cls.policy)

    def baseline(self):
        return load_yaml(normalize_condition(self.raw)[0])

    def test_real_failure_fixed_and_rule_ledger(self):
        self.assertIn("if: ${{ github.ref != 'refs/heads/master' }}", self.output)
        self.assertEqual({"T1", "T2", "T3", "T4"}, {c["rule"] for c in self.changes})
        self.assertEqual(5, len(self.changes))

    def test_idempotence_including_comments_and_format(self):
        again, changes = enhance(self.output, self.source, self.policy)
        self.assertEqual(self.output, again)
        self.assertEqual([], changes)

    def test_repeatability(self):
        for _ in range(3):
            self.assertEqual(self.output, enhance(self.raw, self.source, self.policy)[0])

    def test_yaml_on_is_not_boolean(self):
        result = load_yaml(self.output)
        self.assertIn("on", result)
        self.assertNotIn(True, result)
        self.assertEqual({"push": None, "workflow_dispatch": None}, result["on"])

    def test_preserve_original_behavior_and_env(self):
        before, after = self.baseline(), load_yaml(self.output)
        self.assertEqual(before["concurrency"], after["concurrency"])
        self.assertEqual(before["jobs"]["verify-jdk8"]["env"], after["jobs"]["verify-jdk8"]["env"])
        self.assertEqual(before["jobs"]["verify-jdk8"]["timeout-minutes"], after["jobs"]["verify-jdk8"]["timeout-minutes"])
        self.assertNotIn("container", after["jobs"]["verify-jdk8"])

    def test_changed_command_is_not_replaced_with_hardcoded_verify(self):
        command = "mvn $MAVEN_CLI_OPTS -Dexample=value verify"
        candidate, _ = enhance(self.raw.replace("mvn $MAVEN_CLI_OPTS verify", command),
                               self.source.replace("mvn $MAVEN_CLI_OPTS verify", command), self.policy)
        self.assertIn(command, candidate)

    def test_mismatched_source_command_refused(self):
        with self.assertRaises(Unsupported):
            enhance(self.raw.replace("mvn $MAVEN_CLI_OPTS verify", "mvn $MAVEN_CLI_OPTS package"), self.source, self.policy)

    def test_changed_literal_branch_preserved(self):
        output, _ = enhance(self.raw.replace("refs/heads/master", "refs/heads/release/next"),
                            self.source.replace("    - master", "    - release/next"), self.policy)
        self.assertIn(condition("release/next"), output)

    def test_unknown_yaml_tag_refused(self):
        with self.assertRaises(Unsupported):
            enhance(self.raw.replace("!(github.ref == 'refs/heads/master')", "!something 'true'"), self.source, self.policy)

    def test_duplicate_yaml_keys_refused(self):
        with self.assertRaises(Exception):
            enhance(self.raw + "jobs: {}\n", self.source, self.policy)

    def test_extra_script_refused(self):
        data = self.baseline()
        data["jobs"]["verify-jdk8"]["steps"].append({"run": "echo important"})
        with self.assertRaises(Unsupported):
            enhance(dump_yaml(data), self.source, self.policy)

    def test_malformed_job_shapes_refused(self):
        for jobs in (None, [], {"job": None}, {"job": {"steps": None}}):
            with self.subTest(jobs=jobs):
                data = self.baseline()
                data["jobs"] = jobs
                with self.assertRaises(Unsupported):
                    enhance(dump_yaml(data), self.source, self.policy)

    def test_container_options_refused(self):
        data = self.baseline()
        data["jobs"]["verify-jdk8"]["container"]["options"] = "--privileged"
        with self.assertRaises(Unsupported):
            enhance(dump_yaml(data), self.source, self.policy)

    def test_changed_checkout_directory_refused(self):
        data = self.baseline()
        data["jobs"]["verify-jdk8"]["steps"][0]["with"]["path"] = "nested"
        with self.assertRaises(Unsupported):
            enhance(dump_yaml(data), self.source, self.policy)

    def test_unrecognized_action_not_silently_upgraded(self):
        with self.assertRaises(Unsupported):
            enhance(self.raw.replace("actions/cache@v3.3.2", "third-party/cache@v1"), self.source, self.policy)

    def test_modified_generated_script_refused(self):
        data = load_yaml(self.output)
        data["jobs"]["verify-jdk8"]["steps"][2]["run"] += "exit 0\n"
        with self.assertRaises(Unsupported):
            enhance(dump_yaml(data), self.source, self.policy)

    def test_source_with_extra_job_refused(self):
        with self.assertRaises(Unsupported):
            enhance(self.raw, self.source + "other:\n  script: echo important\n", self.policy)

    def test_unknown_branch_condition_not_rewritten(self):
        with self.assertRaises(Unsupported):
            enhance(self.raw.replace("!(github.ref == 'refs/heads/master')", "always()"), self.source, self.policy)

    def test_script_preserves_failure_exit(self):
        script = load_yaml(self.output)["jobs"]["verify-jdk8"]["steps"][2]["run"]
        self.assertNotIn("|| true", script)
        self.assertNotIn("continue-on-error", self.output)
        self.assertTrue(script.rstrip().endswith("sh -c 'mvn $MAVEN_CLI_OPTS verify'"))
        self.assertIn(self.policy["image_digest"], script)
        self.assertIn('--user "$(id -u):$(id -g)"', script)

    def test_cache_includes_pom_hash_and_toolchain(self):
        inputs = load_yaml(self.output)["jobs"]["verify-jdk8"]["steps"][1]["with"]
        self.assertIn("hashFiles('**/pom.xml')", inputs["key"])
        self.assertIn("jdk8-3.3.9", inputs["key"])
        self.assertEqual(".m2/repository", inputs["path"])

    def test_real_actionlint_baseline_fails_enhanced_passes(self):
        before, _ = lint(DEFAULT_BASELINE)
        if before == "not-run":
            self.skipTest("Optional actionlint not installed")
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "candidate.yml"
            candidate.write_text(self.output, encoding="utf-8")
            after, _ = lint(candidate)
        self.assertEqual("fail", before)
        self.assertEqual("pass", after)

    def test_missing_actionlint_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "candidate.yml"
            candidate.write_text(self.output, encoding="utf-8")
            status, _ = lint(candidate, Path(temporary) / "missing")
        self.assertEqual("not-run", status)

    def test_compare_does_not_modify_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            before, after = Path(temporary) / "before.yml", Path(temporary) / "after.yml"
            before.write_text(self.raw, encoding="utf-8")
            after.write_text(self.output, encoding="utf-8")
            snapshots = before.read_bytes(), after.read_bytes()
            report, _, _ = make_report(before, after, Path(temporary) / "missing")
            self.assertIn("not-run", report)
            self.assertEqual(snapshots, (before.read_bytes(), after.read_bytes()))

    def test_transform_cli_needs_no_external_tools_and_writes_only_yaml(self):
        (ROOT / "output").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as temporary:
            output = Path(temporary) / "result.yml"
            env = dict(os.environ, PATH="")
            result = subprocess.run([sys.executable, str(ROOT / "transform.py"), "--output", str(output)],
                                    capture_output=True, text=True, env=env, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(["result.yml"], [p.name for p in Path(temporary).iterdir()])
            self.assertEqual(self.output, read(output))

    def test_transform_cannot_overwrite_baseline(self):
        original = DEFAULT_BASELINE.read_bytes()
        self.assertEqual(2, main(["--output", str(DEFAULT_BASELINE)]))
        self.assertEqual(original, DEFAULT_BASELINE.read_bytes())


if __name__ == "__main__":
    unittest.main()
