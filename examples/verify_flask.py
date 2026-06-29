import os
from harness.verifier import verify_task

def run_example():
    # Targets a flask repository commit baseline
    repo_url = "https://github.com/pallets/flask.git"
    base_commit = "90a6e8ea3de880c5e7b233a364177c3cfd9d48b1"
    
    # Define a mock reproducer test patch
    test_patch = """diff --git a/tests/test_flask.py b/tests/test_flask.py
--- a/tests/test_flask.py
+++ b/tests/test_flask.py
@@ -1,3 +1,6 @@
+def test_context_reproduction():
+    import flask
+    assert False  # Simulating a failing context test
"""

    # Define a mock patch fixing the issue
    fix_patch = """diff --git a/src/flask/app.py b/src/flask/app.py
--- a/src/flask/app.py
+++ b/src/flask/app.py
@@ -1,2 +1,2 @@
 # Modifying flask app to show the fix patch application
"""

    repo_dir = "./workspace/flask_repo"
    env_dir = "./workspace/flask_venv"

    print("Running verification for flask instance...")
    result = verify_task(
        repo_url=repo_url,
        base_commit=base_commit,
        test_patch=test_patch,
        fix_patch=fix_patch,
        repo_dir=repo_dir,
        env_dir=env_dir,
        test_targets=["tests/test_flask.py"]
    )

    print("\n=== Verification Completed ===")
    print(f"Success: {result.success}")
    print(f"Reproduced (pre-fix test failed): {result.reproduced}")
    print(f"Resolved (post-fix test passed): {result.resolved}")

if __name__ == "__main__":
    run_example()
