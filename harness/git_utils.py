import subprocess
import os
import shutil
import logging
from typing import List

logger = logging.getLogger("swe-harness.git")

class GitError(Exception):
    """Raised when a Git command execution fails."""
    pass

def _run_git_cmd(args: List[str], cwd: str) -> subprocess.CompletedProcess:
    """Executes a Git command as a subprocess in the specified directory.

    Args:
        args: Command-line arguments for Git (excluding the 'git' executable).
        cwd: Working directory where the command should be run.

    Returns:
        CompletedProcess: The finished subprocess execution metadata.

    Raises:
        GitError: If the subprocess execution encounters an system error.
    """
    cmd = ["git"] + args
    logger.debug("Running git command: %s in %s", " ".join(cmd), cwd)
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if result.returncode != 0:
            logger.debug("Git command failed. stdout: %s, stderr: %s", result.stdout, result.stderr)
        return result
    except Exception as e:
        raise GitError(f"Failed to execute git command {' '.join(cmd)}: {e}") from e

def clone_repo(repo_url: str, dest_dir: str) -> None:
    """Clones a Git repository to a local destination path.

    Cleans the target destination directory if it already exists.

    Args:
        repo_url: The Git clone URL.
        dest_dir: Destination path to clone the repository into.

    Raises:
        GitError: If cloning fails or destination cleaning fails.
    """
    if os.path.exists(dest_dir):
        logger.warning("Destination path %s already exists. Cleaning up...", dest_dir)
        try:
            # Handle read-only files on Windows during removal
            def remove_readonly(func, path, exc_info):
                os.chmod(path, 0o777)
                func(path)
            shutil.rmtree(dest_dir, onerror=remove_readonly)
        except Exception as e:
            raise GitError(f"Failed to clear existing destination path {dest_dir}: {e}") from e

    parent_dir = os.path.dirname(dest_dir)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    logger.info("Cloning %s into %s...", repo_url, dest_dir)
    try:
        result = subprocess.run(
            ["git", "clone", repo_url, dest_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if result.returncode != 0:
            raise GitError(f"Clone failed with exit code {result.returncode}: {result.stderr}")
    except Exception as e:
        if isinstance(e, GitError):
            raise
        raise GitError(f"Failed to execute clone command: {e}") from e

def checkout_commit(repo_dir: str, commit_hash: str) -> None:
    """Checks out a target Git reference (branch, tag, or commit hash).

    Args:
        repo_dir: Path to the local Git repository.
        commit_hash: The target Git reference to check out.

    Raises:
        GitError: If the checkout operation fails.
    """
    logger.info("Checking out reference %s in %s...", commit_hash, repo_dir)
    result = _run_git_cmd(["checkout", commit_hash], cwd=repo_dir)
    if result.returncode != 0:
        raise GitError(f"Checkout failed for reference {commit_hash}: {result.stderr}")

def clean_and_reset(repo_dir: str) -> None:
    """Hard-resets the working directory and cleans untracked build artifacts.

    Args:
        repo_dir: Path to the local Git repository.

    Raises:
        GitError: If reset or clean operations fail.
    """
    logger.info("Resetting and cleaning working directory in %s...", repo_dir)
    
    reset_res = _run_git_cmd(["reset", "--hard", "HEAD"], cwd=repo_dir)
    if reset_res.returncode != 0:
        raise GitError(f"Hard reset failed: {reset_res.stderr}")
    
    clean_res = _run_git_cmd(["clean", "-fdx"], cwd=repo_dir)
    if clean_res.returncode != 0:
        raise GitError(f"Clean failed: {clean_res.stderr}")

def check_patch(repo_dir: str, patch_path: str) -> bool:
    """Dry-runs a git apply operation to verify if a patch applies cleanly.

    Args:
        repo_dir: Path to the local Git repository.
        patch_path: Absolute path to the local diff/patch file.

    Returns:
        bool: True if the patch can be applied cleanly, False otherwise.
    """
    logger.info("Verifying patch application dry-run for %s...", patch_path)
    result = _run_git_cmd(["apply", "--check", patch_path], cwd=repo_dir)
    return result.returncode == 0

def apply_patch(repo_dir: str, patch_path: str) -> None:
    """Applies a patch file to the Git working directory.

    Args:
        repo_dir: Path to the local Git repository.
        patch_path: Absolute path to the patch file.

    Raises:
        GitError: If patch application fails.
    """
    logger.info("Applying patch %s...", patch_path)
    result = _run_git_cmd(["apply", patch_path], cwd=repo_dir)
    if result.returncode != 0:
        raise GitError(f"Failed to apply patch {patch_path}: {result.stderr}")

def apply_patch_content(repo_dir: str, patch_content: str) -> None:
    """Writes patch content to a temp file and applies it to the Git directory.

    Args:
        repo_dir: Path to the local Git repository.
        patch_content: Raw diff/patch content as a string.

    Raises:
        GitError: If patch application fails.
    """
    temp_patch = os.path.join(repo_dir, "temp_harness_patch.patch")
    try:
        with open(temp_patch, "w", encoding="utf-8", newline="\n") as f:
            f.write(patch_content)
        apply_patch(repo_dir, temp_patch)
    finally:
        if os.path.exists(temp_patch):
            os.remove(temp_patch)

def get_current_commit(repo_dir: str) -> str:
    """Retrieves the full SHA-1 hash of the HEAD commit.

    Args:
        repo_dir: Path to the local Git repository.

    Returns:
        str: The 40-character commit hash string.

    Raises:
        GitError: If rev-parse operation fails.
    """
    result = _run_git_cmd(["rev-parse", "HEAD"], cwd=repo_dir)
    if result.returncode != 0:
        raise GitError(f"Failed to resolve current commit SHA: {result.stderr}")
    return result.stdout.strip()
