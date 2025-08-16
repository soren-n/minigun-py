#!/usr/bin/env python3
"""
Git commit message validator for conventional commits.
Install as a commit-msg hook to validate commit messages locally.

To install:
    ln -s ../../scripts/commit_msg_hook.py .git/hooks/commit-msg
    chmod +x .git/hooks/commit-msg
"""

import re
import sys
from pathlib import Path


def validate_commit_message(message: str) -> bool:
    """Validate if commit message follows conventional commits format."""
    # Pattern for conventional commits
    pattern = (
        r"^(build|chore|ci|docs|feat|fix|perf|refactor|style|test)(\(.+\))?!?: .{1,50}"
    )

    # Check if message matches pattern
    if not re.match(pattern, message):
        return False

    # Additional checks
    lines = message.split("\n")

    # Subject line should not end with period
    if lines[0].endswith("."):
        return False

    # If there's a body, there should be a blank line after subject
    if len(lines) > 1 and lines[1].strip() != "":
        return False

    return True


def main():
    if len(sys.argv) != 2:
        print("Usage: commit-msg <commit-msg-file>")
        sys.exit(1)

    commit_msg_file = Path(sys.argv[1])

    if not commit_msg_file.exists():
        print(f"Commit message file {commit_msg_file} not found")
        sys.exit(1)

    commit_message = commit_msg_file.read_text().strip()

    # Skip validation for merge commits
    if commit_message.startswith("Merge "):
        sys.exit(0)

    if not validate_commit_message(commit_message):
        print("❌ Invalid commit message format!")
        print()
        print("Commit messages should follow conventional commits format:")
        print("  <type>[optional scope]: <description>")
        print()
        print(
            "Valid types: build, chore, ci, docs, feat, fix, perf, refactor, style, test"
        )
        print()
        print("Examples:")
        print("  feat: add new arbitrary combinator")
        print("  fix: resolve memory leak in generator")
        print("  docs: update API documentation")
        print("  feat!: redesign core API (breaking change)")
        print()
        print("See SEMANTIC_VERSIONING.md for more details.")
        sys.exit(1)

    print("✅ Commit message format is valid")
    sys.exit(0)


if __name__ == "__main__":
    main()
