"""The decision package is the last gate before promotion, so it gets hostile input.

Every case here returned PASS from the previous validator, which never loaded
decision-output.schema.json and could not see a red-team disposition at all.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "modules/idea-expander-decision-node/scripts/validate_decision_package.py"
VALID = ROOT / "modules/idea-expander-decision-node/tests/decision-package.valid.json"


class DecisionPackageTests(unittest.TestCase):
    def run_validator(self, package, tmp_name):
        path = ROOT / "tests" / tmp_name
        path.write_text(json.dumps(package), encoding="utf-8")
        try:
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)], capture_output=True, text=True
            )
        finally:
            path.unlink(missing_ok=True)

    def package(self):
        return json.loads(VALID.read_text(encoding="utf-8"))

    def test_supplied_fixture_passes(self):
        result = self.run_validator(self.package(), "_tmp_valid.json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unknown_decision_value_is_rejected(self):
        package = self.package()
        package["decision"] = "BANANA"
        result = self.run_validator(package, "_tmp_banana.json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("decision", result.stdout)

    def test_integer_board_vote_is_rejected(self):
        package = self.package()
        package["board_votes"][0]["vote"] = 3
        self.assertEqual(self.run_validator(package, "_tmp_intvote.json").returncode, 1)

    def test_go_with_unresolved_critical_finding_is_rejected(self):
        """red-team-protocol.md: unresolved critical findings force HOLD or NO_GO."""
        package = self.package()
        package["red_team"]["findings"][0]["disposition"] = "unresolved"
        package["decision"] = "GO"
        package["conditions"] = []
        result = self.run_validator(package, "_tmp_go_unresolved.json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unresolved critical findings force HOLD or NO_GO", result.stdout)

    def test_conditional_go_with_unresolved_critical_finding_is_rejected(self):
        package = self.package()
        package["red_team"]["findings"][0]["disposition"] = "unresolved"
        self.assertEqual(self.run_validator(package, "_tmp_cgo_unresolved.json").returncode, 1)

    def test_unconditional_go_over_a_conditioned_critical_finding_is_rejected(self):
        """polycognitive-board.md: any confirmed fatal blocker prevents unconditional GO."""
        package = self.package()
        package["decision"] = "GO"
        package["conditions"] = []
        result = self.run_validator(package, "_tmp_go_conditioned.json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unconditional GO is not permitted", result.stdout)

    def test_conditional_go_without_gates_is_rejected(self):
        """polycognitive-board.md: CONDITIONAL_GO requires executable gates."""
        package = self.package()
        package["conditions"] = []
        self.assertEqual(self.run_validator(package, "_tmp_cgo_nogate.json").returncode, 1)

    def test_condition_without_a_trigger_is_rejected(self):
        package = self.package()
        del package["conditions"][0]["trigger"]
        self.assertEqual(self.run_validator(package, "_tmp_notrigger.json").returncode, 1)

    def test_minority_vote_without_dissent_register_is_rejected(self):
        """polycognitive-board.md: preserve every member's memo and minority vote."""
        package = self.package()
        package["dissent"] = []
        result = self.run_validator(package, "_tmp_nodissent.json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("dissent register is empty", result.stdout)

    def test_output_must_bind_to_the_adjudicated_input(self):
        package = self.package()
        del package["decision_node_input_digest"]
        self.assertEqual(self.run_validator(package, "_tmp_nodigest.json").returncode, 1)


if __name__ == "__main__":
    unittest.main()
