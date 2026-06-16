import os
import json
import logging
from typing import List, Dict, Any, Optional
from harness.env_utils import run_in_venv

logger = logging.getLogger("swe-harness.test_runner")

class TestRunnerError(Exception):
    """Raised when test execution or coverage reporting fails."""
    pass

def determine_test_framework(repo_dir: str) -> str:
    """Detects the testing framework used in the target repository.

    Scans files like pyproject.toml, setup.cfg, and imports in tests/ to
    identify if pytest or unittest should be used.

    Args:
        repo_dir: Path to the target Git repository.

    Returns:
        str: Either 'pytest' or 'unittest'. Defaults to 'pytest'.
    """
    pyproject_path = os.path.join(repo_dir, "pyproject.toml")
    setup_cfg_path = os.path.join(repo_dir, "setup.cfg")
    pytest_ini_path = os.path.join(repo_dir, "pytest.ini")

    if os.path.exists(pytest_ini_path):
        return "pytest"

    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, "r", encoding="utf-8") as f:
                content = f.read()
                if "[tool.pytest" in content or "pytest" in content:
                    return "pytest"
        except Exception:
            pass

    if os.path.exists(setup_cfg_path):
        try:
            with open(setup_cfg_path, "r", encoding="utf-8") as f:
                content = f.read()
                if "[tool:pytest]" in content or "[pytest]" in content:
                    return "pytest"
        except Exception:
            pass

    tests_dir = os.path.join(repo_dir, "tests")
    if os.path.exists(tests_dir):
        for root, _, files in os.walk(tests_dir):
            for file in files:
                if file.endswith(".py"):
                    try:
                        with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                            if "import pytest" in f.read():
                                return "pytest"
                    except Exception:
                        pass

    return "pytest"

def run_tests(
    repo_dir: str,
    env_dir: str,
    test_targets: Optional[List[str]] = None,
    collect_coverage: bool = False
) -> Dict[str, Any]:
    """Runs a test suite in the virtualenv, optionally collecting coverage.

    Args:
        repo_dir: Path to the target Git repository.
        env_dir: Path to the local virtual environment.
        test_targets: List of specific test file paths or names to target.
        collect_coverage: If True, uses coverage.py to compile metrics.

    Returns:
        Dict[str, Any]: Test results containing exit_code, passed status,
            stdout, stderr, and parsed coverage dictionary.
    """
    framework = determine_test_framework(repo_dir)
    logger.info("Using test framework: %s", framework)

    cmd = []
    if collect_coverage:
        cmd = ["python", "-m", "coverage", "run", "--source", repo_dir]
        if framework == "pytest":
            cmd += ["-m", "pytest"]
        else:
            cmd += ["-m", "unittest"]
    else:
        if framework == "pytest":
            cmd = ["python", "-m", "pytest"]
        else:
            cmd = ["python", "-m", "unittest", "discover"]

    if test_targets:
        cmd += test_targets

    logger.info("Running test command: %s", " ".join(cmd))
    res = run_in_venv(cmd, env_dir, cwd=repo_dir)

    test_results = {
        "exit_code": res.returncode,
        "passed": res.returncode == 0,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "coverage": None
    }

    if collect_coverage:
        try:
            test_results["coverage"] = _extract_coverage_data(repo_dir, env_dir)
        except Exception as e:
            logger.error("Failed to parse coverage data: %s", e)
            test_results["coverage"] = {"error": str(e)}

    return test_results

def _extract_coverage_data(repo_dir: str, env_dir: str) -> Dict[str, Any]:
    """Compiles coverage database into a temporary JSON file and parses it.

    Args:
        repo_dir: Path to the target Git repository.
        env_dir: Path to the local virtual environment.

    Returns:
        Dict[str, Any]: Parsed code coverage statistics including total cover
            percentage and file-level metrics.
    """
    json_report_path = os.path.join(repo_dir, "temp_coverage.json")
    dot_coverage_path = os.path.join(repo_dir, ".coverage")
    
    if not os.path.exists(dot_coverage_path):
        logger.warning("No .coverage database found at %s", dot_coverage_path)
        return {"total_coverage_percent": 0.0, "files": {}}

    cmd = ["python", "-m", "coverage", "json", "-o", json_report_path]
    res = run_in_venv(cmd, env_dir, cwd=repo_dir)
    if res.returncode != 0:
        logger.error("Failed to generate coverage JSON report: %s", res.stderr)
        return {"total_coverage_percent": 0.0, "files": {}}

    if not os.path.exists(json_report_path):
        logger.error("Coverage report file was not created at %s", json_report_path)
        return {"total_coverage_percent": 0.0, "files": {}}

    try:
        with open(json_report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        summary = data.get("totals", {})
        total_percent = summary.get("percent_covered", 0.0)
        
        files_data = {}
        for filepath, file_info in data.get("files", {}).items():
            rel_path = os.path.relpath(filepath, repo_dir)
            files_data[rel_path] = {
                "percent_covered": file_info.get("summary", {}).get("percent_covered", 0.0),
                "missing_lines": file_info.get("missing_lines", []),
                "excluded_lines": file_info.get("excluded_lines", [])
            }

        return {
            "total_coverage_percent": total_percent,
            "files": files_data
        }
    finally:
        if os.path.exists(json_report_path):
            os.remove(json_report_path)
        if os.path.exists(dot_coverage_path):
            os.remove(dot_coverage_path)
