#!/usr/bin/env python3
"""
Setup script for semantic versioning development environment.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False


def setup_git_hooks():
    """Setup git hooks for commit message validation."""
    git_dir = Path(".git")
    if not git_dir.exists():
        print("❌ Not in a git repository")
        return False

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    commit_msg_hook = hooks_dir / "commit-msg"
    hook_script = Path("scripts/commit_msg_hook.py").resolve()

    if commit_msg_hook.exists():
        commit_msg_hook.unlink()

    # Create symlink to the hook script
    commit_msg_hook.symlink_to(hook_script)
    commit_msg_hook.chmod(0o755)

    print("✅ Git commit-msg hook installed")
    return True


def main():
    print("🚀 Setting up semantic versioning environment...\n")

    # Install python-semantic-release as a dev tool
    if not run_command(
        ["uv", "tool", "install", "python-semantic-release"],
        "Installing python-semantic-release",
    ):
        return 1

    # Setup git hooks
    if not setup_git_hooks():
        return 1

    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Make sure PYPI_API_TOKEN is set in GitHub repository secrets")
    print("2. Start using conventional commit messages:")
    print("   - feat: for new features (minor version bump)")
    print("   - fix: for bug fixes (patch version bump)")
    print("   - feat!: for breaking changes (major version bump)")
    print("3. Push to main branch to trigger automatic releases")
    print("\nSee SEMANTIC_VERSIONING.md for detailed usage instructions.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
