import os
import sys
import shutil
import tempfile
import unittest
import subprocess
from unittest.mock import patch

from harness import git_utils
from harness import env_utils
from harness import test_runner
from harness import verifier

class TestSweHarness(unittest.TestCase):
    """Unit tests for the Git and Verification workflow modules."""

    def setUp(self) -> None:
        """Sets up a local Git repository to mock verification targets."""
        self.test_dir = tempfile.mkdtemp()
        self.source_repo_dir = os.path.join(self.test_dir, "source_repo")
        self.clone_repo_dir = os.path.join(self.test_dir, "clone_repo")
        self.mock_env_dir = os.path.join(self.test_dir, "mock_venv")

        os.makedirs(self.source_repo_dir, exist_ok=True)
        
        self._run_cmd(["git", "init"], cwd=self.source_repo_dir)
        self._run_cmd(["git", "config", "user.email", "test-harness@example.com"], cwd=self.source_repo_dir)
        self._run_cmd(["git", "config", "user.name", "Harness Tester"], cwd=self.source_repo_dir)

        # Create a basic codebase with a subtraction bug in addition
        self.calc_py_path = os.path.join(self.source_repo_dir, "calc.py")
        with open(self.calc_py_path, "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a - b\n")

        self.test_calc_py_path = os.path.join(self.source_repo_dir, "test_calc.py")
        with open(self.test_calc_py_path, "w", encoding="utf-8") as f:
            f.write("from calc import add\ndef test_sanity():\n    assert True\n")

        self._run_cmd(["git", "add", "calc.py", "test_calc.py"], cwd=self.source_repo_dir)
        self._run_cmd(["git", "commit", "-m", "baseline commit"], cwd=self.source_repo_dir)
        
        res = self._run_cmd(["git", "rev-parse", "HEAD"], cwd=self.source_repo_dir)
        self.base_commit = res.stdout.strip()

        # Diff representing a failing test case reproducing the bug
        self.test_patch = (
            "diff --git a/test_calc.py b/test_calc.py\n"
            "--- a/test_calc.py\n"
            "+++ b/test_calc.py\n"
            "@@ -2,2 +2,4 @@ from calc import add\n"
            " def test_sanity():\n"
            "     assert True\n"
            "+def test_add_correctness():\n"
            "+    assert add(2, 3) == 5\n"
        )

        # Diff representing the code fix
        self.fix_patch = (
            "diff --git a/calc.py b/calc.py\n"
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def add(a, b):\n"
            "-    return a - b\n"
            "+    return a + b\n"
        )

    def tearDown(self) -> None:
        """Cleans up temporary directory paths."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run_cmd(self, args: list, cwd: str) -> subprocess.CompletedProcess:
        res = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Command failed: {args}. Stderr: {res.stderr}")
        return res

    def test_git_utils_and_patch_extraction(self) -> None:
        """Verifies patch extraction, repository cloning, and patch verification."""
        files = verifier.extract_files_from_patch(self.fix_patch)
        self.assertEqual(files, ["calc.py"])

        git_utils.clone_repo(self.source_repo_dir, self.clone_repo_dir)
        self.assertTrue(os.path.exists(os.path.join(self.clone_repo_dir, ".git")))
        
        current = git_utils.get_current_commit(self.clone_repo_dir)
        self.assertEqual(current, self.base_commit)

        patch_file = os.path.join(self.test_dir, "test.patch")
        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(self.test_patch)

        applies = git_utils.check_patch(self.clone_repo_dir, patch_file)
        self.assertTrue(applies)

    @patch("harness.env_utils.create_virtualenv")
    @patch("harness.env_utils.install_dependencies")
    @patch("harness.env_utils.resolve_venv_executables")
    @patch("harness.env_utils.get_venv_env_vars")
    @patch("harness.test_runner.run_tests")
    def test_end_to_end_verification_workflow(
        self, mock_run_tests, mock_get_env_vars, mock_resolve_execs, mock_install_deps, mock_create_venv
    ) -> None:
        """Simulates the full verification run using mocks for virtualenv subprocesses."""
        mock_create_venv.return_value = {"python": sys.executable, "pip": "mock_pip"}
        mock_resolve_execs.return_value = {"python": sys.executable, "pip": "mock_pip"}
        mock_get_env_vars.return_value = os.environ.copy()

        def run_tests_side_effect(repo_dir, env_dir, test_targets=None, collect_coverage=False):
            if not collect_coverage:
                return {
                    "exit_code": 1,
                    "passed": False,
                    "stdout": "FAIL: test_add_correctness",
                    "stderr": "",
                    "coverage": None
                }
            return {
                "exit_code": 0,
                "passed": True,
                "stdout": "PASS: test_add_correctness",
                "stderr": "",
                "coverage": {
                    "total_coverage_percent": 90.0,
                    "files": {
                        os.path.join(repo_dir, "calc.py"): {
                            "percent_covered": 100.0,
                            "missing_lines": []
                        }
                    }
                }
            }
        mock_run_tests.side_effect = run_tests_side_effect

        report = verifier.verify_task(
            repo_url=self.source_repo_dir,
            base_commit=self.base_commit,
            test_patch=self.test_patch,
            fix_patch=self.fix_patch,
            repo_dir=self.clone_repo_dir,
            env_dir=self.mock_env_dir,
            test_targets=["test_calc.py"]
        )

        # Verify results
        self.assertTrue(report.reproduced)
        self.assertTrue(report.resolved)
        self.assertTrue(report.success)
        self.assertEqual(report.modified_files, ["calc.py"])
        self.assertFalse(os.path.exists(os.path.join(self.clone_repo_dir, "temp_harness_patch.patch")))
        
if __name__ == "__main__":
    unittest.main()
