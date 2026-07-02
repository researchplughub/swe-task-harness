import os
import sys
import getpass
import urllib.request
import json
import subprocess

def run_cmd(args):
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        return False, res.stderr
    return True, res.stdout

def main():
    print("=== Push swe-task-harness to GitHub ===")
    username = input("Enter your GitHub username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
        
    print("\nTo push, you need a GitHub Personal Access Token (PAT) with 'repo' scope.")
    print("If you don't have one, go to https://github.com/settings/tokens to generate a Classic Token with 'repo' checkbox selected.")
    token = getpass.getpass("Enter your GitHub PAT (typing is hidden): ").strip()
    if not token:
        print("Token cannot be empty.")
        return

    # 1. Create the repository via GitHub API
    print(f"\nCreating repository 'swe-task-harness' on GitHub for user '{username}'...")
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "SWE-Task-Harness-App"
    }
    data = json.dumps({
        "name": "swe-task-harness",
        "description": "A Python toolkit for automating the verification and packaging of software engineering tasks from public Git repositories, inspired by LLM evaluation pipelines.",
        "private": False
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode())
            html_url = res_data.get("html_url")
            print(f"✓ Success! Created repository at {html_url}")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        try:
            err_json = json.loads(err_msg)
            message = err_json.get("message", "")
            # If it already exists, that's fine, we can still push
            if "already_exists" in str(err_json) or "already exists" in message or e.code == 422:
                print("✓ Repository already exists on GitHub. Proceeding to push...")
            else:
                print(f"✗ HTTP Error {e.code}: {message}")
                return
        except Exception:
            print(f"✗ HTTP Error {e.code}: {err_msg}")
            return
    except Exception as e:
        print(f"✗ Error creating repository: {str(e)}")
        return

    # 2. Push to the repository
    print("\nPushing code to GitHub...")
    # Set the remote with token in URL (temporary for push)
    remote_url = f"https://{username}:{token}@github.com/{username}/swe-task-harness.git"
    
    # Check if remote 'origin' already exists
    success, _ = run_cmd(["git", "remote", "get-url", "origin"])
    if success:
        run_cmd(["git", "remote", "remove", "origin"])

    success, err = run_cmd(["git", "remote", "add", "origin", remote_url])
    if not success:
        print(f"✗ Failed to add git remote: {err}")
        return

    # Set branch name to main
    run_cmd(["git", "branch", "-M", "main"])

    # Push to origin main
    print("Running git push (this may take a few seconds)...")
    success, err = run_cmd(["git", "push", "-u", "origin", "main"])
    
    # 3. Clean up credentials from remote URL to be safe!
    clean_url = f"https://github.com/{username}/swe-task-harness.git"
    run_cmd(["git", "remote", "set-url", "origin", clean_url])

    if success:
        print("\n=== SUCCESS ===")
        print(f"Your project is now live at: https://github.com/{username}/swe-task-harness")
    else:
        print(f"\n✗ Push failed: {err}")
        print("Make sure your token has the correct permissions (write access to repositories).")

if __name__ == "__main__":
    main()
