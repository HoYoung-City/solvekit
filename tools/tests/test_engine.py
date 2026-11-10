import copy
import tempfile
import unittest
from pathlib import Path

from methodkit.cli import main
from methodkit.engine import (MethodError, complete_step, load_json, next_batches,
    read_run, render_run, reopen_step, retain_case, revise_run, save_json,
    start_run, validate_pattern, verify_evidence)

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.run = self.base / "run"
        self.pattern = load_json(ROOT / "patterns/build.json")
        start_run(self.pattern, self.run, "Explain an input file")

    def tearDown(self):
        self.tmp.cleanup()

    def finish(self, step):
        artifact = self.run / "evidence" / f"{step}.txt"
        artifact.parent.mkdir(exist_ok=True)
        artifact.write_text(f"Synthetic test evidence for {step}\n", encoding="utf-8")
        complete_step(self.run, step, "Synthetic result", [f"evidence/{step}.txt"])

    def baseline(self):
        for step in ("frame", "structure", "baseline", "baseline-check"):
            self.finish(step)

    def finish_all(self):
        for step in self.pattern["steps"]:
            self.finish(step["id"])

    def test_rejects_execution_before_dependencies(self):
        with self.assertRaisesRegex(MethodError, "Dependencies"):
            self.finish("baseline")

    def test_rejects_missing_evidence(self):
        with self.assertRaises(MethodError):
            complete_step(self.run, "frame", "Claimed done", ["missing.txt"])

    def test_evidence_must_be_inside_run(self):
        outside = self.base / "outside.txt"
        outside.write_text("private")
        with self.assertRaises(MethodError):
            complete_step(self.run, "frame", "result", ["../outside.txt"])

    def test_independent_ready_work_is_batched(self):
        self.baseline()
        self.assertEqual([[s["id"] for s in b] for b in next_batches(self.run)],
                         [["core", "experience"]])

    def test_shared_write_resource_requires_separate_batches(self):
        pattern = copy.deepcopy(self.pattern)
        for step in pattern["steps"]:
            if step["id"] in ("core", "experience"):
                step["writes"] = ["shared-component"]
        alternative = self.base / "conflict"
        start_run(pattern, alternative, "goal")
        self.run = alternative
        self.baseline()
        self.assertEqual(len(next_batches(self.run)), 2)

    def test_changed_evidence_blocks_next_work(self):
        self.finish("frame")
        (self.run / "evidence/frame.txt").write_text("changed")
        with self.assertRaisesRegex(MethodError, "changed"):
            next_batches(self.run)

    def test_reopen_invalidates_descendants_but_not_sibling(self):
        self.finish_all()
        affected = reopen_step(self.run, "core", "New evidence")
        self.assertEqual(set(affected), {"core", "integrate", "validate", "explain"})
        run = read_run(self.run)
        self.assertEqual(run["steps"]["experience"]["status"], "done")
        self.assertEqual(run["history"][-1]["previous_results"]["core"]["status"], "done")

    def test_plan_changes_require_explicit_revision_record(self):
        self.finish("frame")
        run = load_json(self.run / "run.json")
        run["problem"]["constraints"] = ["new constraint"]
        save_json(self.run / "run.json", run)
        with self.assertRaisesRegex(MethodError, "revise"):
            next_batches(self.run)
        revise_run(self.run, "Changed constraint")
        self.assertEqual(read_run(self.run)["steps"]["frame"]["status"], "pending")

    def test_success_cannot_be_retained_from_partial_work(self):
        self.finish("frame")
        with self.assertRaises(MethodError):
            retain_case(self.run, "success", "lesson", self.base / "case.json")

    def test_failure_is_retained_as_candidate(self):
        case = retain_case(self.run, "failure", "Inputs were insufficient", self.base / "case.json")
        self.assertEqual(case["status"], "candidate")
        self.assertEqual(case["outcome"], "failure")

    def test_completed_run_retains_without_auto_promotion(self):
        self.finish_all()
        case = retain_case(self.run, "success", "Use a complete first result", self.base / "case.json")
        self.assertEqual(case["status"], "candidate")
        verify_evidence(self.run, read_run(self.run))

    def test_cycle_and_unknown_dependency_are_rejected(self):
        pattern = copy.deepcopy(self.pattern)
        pattern["steps"][0]["depends_on"] = ["explain"]
        with self.assertRaisesRegex(MethodError, "cycle"):
            validate_pattern(pattern)
        pattern["steps"][0]["depends_on"] = ["absent"]
        with self.assertRaisesRegex(MethodError, "Unknown dependency"):
            validate_pattern(pattern)

    def test_report_contains_all_levels_and_stable_step_ids(self):
        report = render_run(self.run).read_text()
        for level in ("L0", "L1", "L2", "L3"):
            self.assertIn(level, report)
        self.assertIn("core --> integrate", report)
        self.assertIn("experience --> integrate", report)

    def test_existing_run_is_not_overwritten(self):
        with self.assertRaises(MethodError):
            start_run(self.pattern, self.run, "different goal")

    def test_cli_reports_failure_for_unready_step(self):
        self.assertEqual(main(["complete", str(self.run), "baseline", "--result", "x",
                               "--evidence", "absent.txt"]), 2)


if __name__ == "__main__":
    unittest.main()
