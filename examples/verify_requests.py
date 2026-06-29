import os
from harness.verifier import verify_task

def run_example():
    # Targets a historical commit in the Requests repository
    repo_url = "https://github.com/psf/requests.git"
    base_commit = "d628d0859c25f17d3d0f0eb850e04771d9d48b11"
    
    # Define a mock reproducer test patch
    test_patch = """diff --git a/tests/test_requests.py b/tests/test_requests.py
--- a/tests/test_requests.py
+++ b/tests/test_requests.py
@@ -1,3 +1,6 @@
+def test_api_reproduction():
+    import requests
+    assert False  # Simulating a failing test checking requests behavior
"""

    # Define a mock patch fixing the issue
    fix_patch = """diff --git a/requests/models.py b/requests/models.py
--- a/requests/models.py
+++ b/requests/models.py
@@ -1,2 +1,2 @@
 # Modifying requests models to show the fix patch application
"""

    repo_dir = "./workspace/requests_repo"
    env_dir = "./workspace/requests_venv"

    print("Running verification for requests instance...")
    result = verify_task(
        repo_url=repo_url,
        base_commit=base_commit,
        test_patch=test_patch,
        fix_patch=fix_patch,
        repo_dir=repo_dir,
        env_dir=env_dir,
        test_targets=["tests/test_requests.py"]
    )

    print("\n=== Verification Completed ===")
    print(f"Success: {result.success}")
    print(f"Reproduced (pre-fix test failed): {result.reproduced}")
    print(f"Resolved (post-fix test passed): {result.resolved}")

if __name__ == "__main__":
    run_example()
