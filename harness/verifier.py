import os
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

from harness import git_utils
from harness import env_utils
from harness import test_runner

logger = logging.getLogger("swe-harness.verifier")

class VerificationError(Exception):
    """Raised when task verification encounters an unrecoverable failure."""
    pass

@dataclass
class TestSummary:
    """Represents a summary of a test runner execution phase."""
    exit_code: Optional[int] = None
    passed: bool = False
    stdout_snippet: str = ""
    stderr_snippet: str = ""

@dataclass
class FileCoverage:
    """Represents coverage statistics for a single code file."""
    percent_covered: float = 0.0
    missing_lines: Any = field(default_factory=list)  # list of ints or string error message

@dataclass
class CoverageSummary:
    """Represents package-wide and file-specific coverage details."""
    total_coverage_percent: float = 0.0
    modified_files_coverage: Dict[str, FileCoverage] = field(default_factory=dict)

@dataclass
class VerificationResult:
    """Represents the outcome of the repository verification workflow."""
    repo_url: str
    base_commit: str
    reproduced: bool = False
    resolved: bool = False
    pre_fix_test_summary: TestSummary = field(default_factory=TestSummary)
    post_fix_test_summary: TestSummary = field(default_factory=TestSummary)
    modified_files: List[str] = field(default_factory=list)
    fix_coverage: Optional[CoverageSummary] = None
    success: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts the dataclass instance to a standard dictionary."""
        return asdict(self)

def extract_files_from_patch(patch_content: str) -> List[str]:
    """Parses a git diff patch to extract files added or modified.

    Args:
        patch_content: Raw diff content.

    Returns:
        List[str]: Relative paths of modified files.
    """
    modified_files = []
    for line in patch_content.splitlines():
        if line.startswith("+++ b/"):
            file_path = line[6:].strip()
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]
            modified_files.append(file_path)
    return modified_files

def verify_task(
    repo_url: str,
    base_commit: str,
    test_patch: str,
    fix_patch: str,
    repo_dir: str,
    env_dir: str,
    test_targets: Optional[List[str]] = None,
) -> VerificationResult:
    """Runs the two-stage execution pipeline to verify a code patch.

    Workflow:
        1. Clones repository and checks out base_commit.
        2. Configures isolated virtualenv and installs dependencies.
        3. Applies reproducing test_patch.
        4. Runs tests (expected to fail).
        5. Applies code fix_patch.
        6. Runs tests (expected to pass).
        7. Collects coverage and formats verification report.

    Args:
        repo_url: Target Git repository clone URL.
        base_commit: Git commit SHA representing the task baseline.
        test_patch: Git patch containing the reproducing test cases.
        fix_patch: Git patch containing the code modifications.
        repo_dir: Directory where repository will be cloned.
        env_dir: Directory where virtual environment will be created.
        test_targets: Optional list of test file paths to restrict run to.

    Returns:
        VerificationResult: Object detailing reproduction, resolution, and coverage.
    """
    logger.info("Starting verification workflow...")
    
    result = VerificationResult(
        repo_url=repo_url,
        base_commit=base_commit,
        pre_fix_test_summary=TestSummary(),
        post_fix_test_summary=TestSummary()
    )

    try:
        git_utils.clone_repo(repo_url, repo_dir)
        git_utils.checkout_commit(repo_dir, base_commit)

        env_utils.create_virtualenv(env_dir)
        env_utils.install_dependencies(
            repo_dir=repo_dir,
            env_dir=env_dir,
            extra_packages=["pytest", "coverage"]
        )

        logger.info("Applying test patch...")
        git_utils.apply_patch_content(repo_dir, test_patch)

        logger.info("Executing pre-fix tests...")
        pre_fix_results = test_runner.run_tests(
            repo_dir=repo_dir,
            env_dir=env_dir,
            test_targets=test_targets,
            collect_coverage=False
        )
        
        result.pre_fix_test_summary = TestSummary(
            exit_code=pre_fix_results["exit_code"],
            passed=pre_fix_results["passed"],
            stdout_snippet=pre_fix_results["stdout"][-1000:] if pre_fix_results["stdout"] else "",
            stderr_snippet=pre_fix_results["stderr"][-1000:] if pre_fix_results["stderr"] else ""
        )

        if pre_fix_results["passed"]:
            logger.warning("Pre-fix tests passed on baseline commit; reproduction failed.")
            result.reproduced = False
        else:
            logger.info("Pre-fix tests failed as expected; reproduction successful.")
            result.reproduced = True

        logger.info("Applying fix patch...")
        git_utils.apply_patch_content(repo_dir, fix_patch)

        modified_files = extract_files_from_patch(fix_patch)
        result.modified_files = modified_files

        logger.info("Executing post-fix tests...")
        post_fix_results = test_runner.run_tests(
            repo_dir=repo_dir,
            env_dir=env_dir,
            test_targets=test_targets,
            collect_coverage=True
        )

        result.post_fix_test_summary = TestSummary(
            exit_code=post_fix_results["exit_code"],
            passed=post_fix_results["passed"],
            stdout_snippet=post_fix_results["stdout"][-1000:] if post_fix_results["stdout"] else "",
            stderr_snippet=post_fix_results["stderr"][-1000:] if post_fix_results["stderr"] else ""
        )

        if post_fix_results["passed"]:
            logger.info("Post-fix tests passed; resolution successful.")
            result.resolved = True
        else:
            logger.warning("Post-fix tests failed; resolution failed.")
            result.resolved = False

        if post_fix_results["coverage"] and not isinstance(post_fix_results["coverage"], str) and "error" not in post_fix_results["coverage"]:
            cov_data = post_fix_results["coverage"]
            result.fix_coverage = CoverageSummary(
                total_coverage_percent=cov_data.get("total_coverage_percent", 0.0),
                modified_files_coverage={}
            )
            
            for file in modified_files:
                norm_file = os.path.normpath(file).replace("\\", "/")
                matched = False
                for cov_file, info in cov_data.get("files", {}).items():
                    norm_cov_file = os.path.normpath(cov_file).replace("\\", "/")
                    if norm_file in norm_cov_file or norm_cov_file in norm_file:
                        result.fix_coverage.modified_files_coverage[file] = FileCoverage(
                            percent_covered=info.get("percent_covered", 0.0),
                            missing_lines=info.get("missing_lines", [])
                        )
                        matched = True
                        break
                
                if not matched:
                    result.fix_coverage.modified_files_coverage[file] = FileCoverage(
                        percent_covered=0.0,
                        missing_lines="No coverage data recorded (file not executed)"
                    )

        result.success = result.reproduced and result.resolved
        logger.info("Verification completed. Success: %s", result.success)

    except Exception as e:
        logger.error("Error encountered during verification: %s", e)
        result.error = str(e)
        result.success = False
    
    finally:
        try:
            if os.path.exists(repo_dir) and os.path.exists(os.path.join(repo_dir, ".git")):
                git_utils.clean_and_reset(repo_dir)
        except Exception as reset_err:
            logger.warning("Failed to reset repository state: %s", reset_err)

    return result
