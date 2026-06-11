import os
import sys
import venv
import subprocess
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("swe-harness.env")

class EnvError(Exception):
    """Raised when virtual environment provisioning or command execution fails."""
    pass

def create_virtualenv(env_dir: str) -> Dict[str, str]:
    """Creates a sandboxed Python virtual environment inside the target folder.

    Args:
        env_dir: Absolute path where the virtual environment will be created.

    Returns:
        Dict[str, str]: A dictionary containing absolute paths to the 'python'
            and 'pip' executables in the created environment.

    Raises:
        EnvError: If virtualenv creation fails.
    """
    logger.info("Creating virtual environment in %s...", env_dir)
    try:
        venv.create(env_dir, with_pip=True, symlinks=False if os.name == 'nt' else True)
    except Exception as e:
        raise EnvError(f"Failed to create virtual environment in {env_dir}: {e}") from e

    executables = resolve_venv_executables(env_dir)
    logger.debug("Resolved virtualenv executables: %s", executables)
    return executables

def resolve_venv_executables(env_dir: str) -> Dict[str, str]:
    """Locates the paths to python and pip binaries inside a virtual environment.

    Args:
        env_dir: Absolute path of the virtual environment.

    Returns:
        Dict[str, str]: Resolves keys 'python' and 'pip' to their platform-specific binary paths.

    Raises:
        EnvError: If python executable cannot be resolved inside the environment path.
    """
    if os.name == "nt":
        python_exe = os.path.join(env_dir, "Scripts", "python.exe")
        pip_exe = os.path.join(env_dir, "Scripts", "pip.exe")
    else:
        python_exe = os.path.join(env_dir, "bin", "python")
        pip_exe = os.path.join(env_dir, "bin", "pip")

    if not os.path.exists(python_exe):
        for root, _, files in os.walk(env_dir):
            for file in files:
                if file == "python.exe" or (file == "python" and os.name != "nt"):
                    python_exe = os.path.join(root, file)
                if file == "pip.exe" or (file == "pip" and os.name != "nt"):
                    pip_exe = os.path.join(root, file)

    if not os.path.exists(python_exe):
        raise EnvError(f"Python executable not found in virtualenv at {env_dir}")

    return {
        "python": python_exe,
        "pip": pip_exe
    }

def get_venv_env_vars(env_dir: str) -> Dict[str, str]:
    """Generates the environment variables needed to mock virtualenv activation.

    Args:
        env_dir: Absolute path of the virtual environment.

    Returns:
        Dict[str, str]: Copy of system environment variables with prepended PATH
            and VIRTUAL_ENV targets.
    """
    env = os.environ.copy()
    
    bin_dir = os.path.join(env_dir, "Scripts") if os.name == "nt" else os.path.join(env_dir, "bin")
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = env_dir
    
    if "PYTHONHOME" in env:
        del env["PYTHONHOME"]

    return env

def install_dependencies(repo_dir: str, env_dir: str, extra_packages: Optional[List[str]] = None) -> None:
    """Discovers project configuration files and installs dependencies in the venv.

    Args:
        repo_dir: Path to the target Git repository codebase.
        env_dir: Path to the local virtual environment.
        extra_packages: List of additional libraries to install (e.g. pytest, coverage).

    Raises:
        EnvError: If installation of extra verification tools fails.
    """
    executables = resolve_venv_executables(env_dir)
    pip_path = executables["pip"]
    env_vars = get_venv_env_vars(env_dir)

    logger.info("Upgrading pip inside virtualenv...")
    subprocess.run([pip_path, "install", "--upgrade", "pip"], env=env_vars, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    requirements_txt = os.path.join(repo_dir, "requirements.txt")
    pyproject_toml = os.path.join(repo_dir, "pyproject.toml")
    setup_py = os.path.join(repo_dir, "setup.py")

    installed_any = False

    if os.path.exists(requirements_txt):
        logger.info("Installing dependencies from requirements.txt...")
        res = subprocess.run([pip_path, "install", "-r", requirements_txt], env=env_vars, capture_output=True, text=True)
        if res.returncode != 0:
            logger.warning("pip install from requirements.txt exited with code %d. stderr: %s", res.returncode, res.stderr)
        installed_any = True

    if os.path.exists(pyproject_toml):
        logger.info("Installing package from pyproject.toml...")
        res = subprocess.run([pip_path, "install", "-e", repo_dir], env=env_vars, capture_output=True, text=True)
        if res.returncode != 0:
            res = subprocess.run([pip_path, "install", repo_dir], env=env_vars, capture_output=True, text=True)
            if res.returncode != 0:
                logger.warning("pyproject installation failed. stderr: %s", res.stderr)
        installed_any = True

    elif os.path.exists(setup_py) and not installed_any:
        logger.info("Installing package from setup.py...")
        res = subprocess.run([pip_path, "install", "-e", repo_dir], env=env_vars, capture_output=True, text=True)
        if res.returncode != 0:
            res = subprocess.run([pip_path, "install", repo_dir], env=env_vars, capture_output=True, text=True)
            if res.returncode != 0:
                logger.warning("setup.py installation failed. stderr: %s", res.stderr)

    if extra_packages:
        logger.info("Installing execution tools: %s...", ", ".join(extra_packages))
        cmd = [pip_path, "install"] + extra_packages
        res = subprocess.run(cmd, env=env_vars, capture_output=True, text=True)
        if res.returncode != 0:
            raise EnvError(f"Failed to install package dependencies {extra_packages}: {res.stderr}")

def run_in_venv(cmd: List[str], env_dir: str, cwd: str) -> subprocess.CompletedProcess:
    """Runs a command as a subprocess with simulated virtual environment paths active.

    Args:
        cmd: List of command-line arguments to run.
        env_dir: Absolute path to the virtual environment.
        cwd: Directory where the command should execute.

    Returns:
        CompletedProcess: Metadata of the completed subprocess run.

    Raises:
        EnvError: If subprocess system execution fails.
    """
    executables = resolve_venv_executables(env_dir)
    env_vars = get_venv_env_vars(env_dir)
    
    if cmd[0] == "python":
        cmd[0] = executables["python"]
    elif cmd[0] == "pip":
        cmd[0] = executables["pip"]

    logger.debug("Running command in venv: %s (cwd: %s)", " ".join(cmd), cwd)
    try:
        return subprocess.run(
            cmd,
            env=env_vars,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
    except Exception as e:
        raise EnvError(f"Failed to run command {' '.join(cmd)} inside virtual environment: {e}") from e
