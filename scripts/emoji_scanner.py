#!/usr/bin/env python3
"""Emoji scanner quality gate for the minigun project.

This script scans source files for emoji characters and reports them as errors.
Emojis can cause issues in certain environments and may not be appropriate
for production code.
"""

import sys
from pathlib import Path

# Unicode ranges for emoji characters
# Based on Unicode 15.0 specification
EMOJI_RANGES = [
    # Emoticons (U+1F600-U+1F64F)
    (0x1F600, 0x1F64F),
    # Miscellaneous Symbols and Pictographs (U+1F300-U+1F5FF)
    (0x1F300, 0x1F5FF),
    # Transport and Map Symbols (U+1F680-U+1F6FF)
    (0x1F680, 0x1F6FF),
    # Supplemental Symbols and Pictographs (U+1F900-U+1F9FF)
    (0x1F900, 0x1F9FF),
    # Symbols and Pictographs Extended-A (U+1FA70-U+1FAFF)
    (0x1FA70, 0x1FAFF),
    # Additional emoji ranges
    # Dingbats (U+2700-U+27BF) - subset
    (0x2700, 0x27BF),
    # Miscellaneous Symbols (U+2600-U+26FF) - subset
    (0x2600, 0x26FF),
    # Geometric Shapes (U+25A0-U+25FF) - subset for emoji
    (0x25AA, 0x25AB),  # Black small square, white small square
    (0x25B6, 0x25B6),  # Black right-pointing triangle
    (0x25C0, 0x25C0),  # Black left-pointing triangle
    (0x25FB, 0x25FE),  # White/black squares
    # CJK Symbols and Punctuation (subset)
    (0x3030, 0x3030),  # Wavy dash
    (0x303D, 0x303D),  # Part alternation mark
    # Enclosed Alphanumeric Supplement
    (0x1F170, 0x1F251),
    # Enclosed Ideographic Supplement
    (0x1F240, 0x1F248),
]

# Additional single code points for common emoji
EMOJI_SINGLE_POINTS = [
    0x203C,  # Double exclamation mark
    0x2049,  # Exclamation question mark
    0x2122,  # Trade mark sign
    0x2139,  # Information source
    0x2194,  # Left right arrow
    0x2195,  # Up down arrow
    0x2196,  # North west arrow
    0x2197,  # North east arrow
    0x2198,  # South east arrow
    0x2199,  # South west arrow
    0x21A9,  # Leftwards arrow with hook
    0x21AA,  # Rightwards arrow with hook
    0x231A,  # Watch
    0x231B,  # Hourglass
    0x2328,  # Keyboard
    0x23CF,  # Eject symbol
    0x23E9,  # Black right-pointing double triangle
    0x23EA,  # Black left-pointing double triangle
    0x23EB,  # Black up-pointing double triangle
    0x23EC,  # Black down-pointing double triangle
    0x23ED,  # Black right-pointing double triangle with vertical bar
    0x23EE,  # Black left-pointing double triangle with vertical bar
    0x23EF,  # Black right-pointing triangle with double vertical bar
    0x23F0,  # Alarm clock
    0x23F1,  # Stopwatch
    0x23F2,  # Timer clock
    0x23F3,  # Hourglass with flowing sand
    0x23F8,  # Double vertical bar
    0x23F9,  # Black square for stop
    0x23FA,  # Black circle for record
    0x24C2,  # Circled latin capital letter m
    0x25B6,  # Black right-pointing triangle
    0x25C0,  # Black left-pointing triangle
    0x2B05,  # Leftwards black arrow
    0x2B06,  # Upwards black arrow
    0x2B07,  # Downwards black arrow
    0x2B1B,  # Black large square
    0x2B1C,  # White large square
    0x2B50,  # White medium star
    0x2B55,  # Heavy large circle
]

# File extensions to scan
SCANNABLE_EXTENSIONS = {
    ".py",
    ".pyx",
    ".pyi",
    ".md",
    ".rst",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
}

# Directories to ignore
IGNORE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
}

# Files to exempt from emoji scanning (relative to project root)
EXEMPT_FILES = {
    "scripts/emoji_scanner.py",  # Contains emojis in output formatting
    "minigun/reporter.py",  # Contains emojis for rich output formatting
}


def is_emoji_character(char: str) -> bool:
    """Check if a character is an emoji based on Unicode ranges."""
    if not char:
        return False

    code_point = ord(char)

    # Check single code points
    if code_point in EMOJI_SINGLE_POINTS:
        return True

    # Check ranges
    for start, end in EMOJI_RANGES:
        if start <= code_point <= end:
            return True

    return False


def find_emojis_in_text(
    text: str, line_num: int = 1
) -> list[tuple[int, int, str, str]]:
    """Find all emojis in text and return their positions.

    Returns:
        List of tuples: (line_number, column_number, emoji_char, context)
    """
    emojis = []
    lines = text.split("\n")

    for i, line in enumerate(lines, start=line_num):
        for j, char in enumerate(line):
            if is_emoji_character(char):
                # Get some context around the emoji
                start = max(0, j - 10)
                end = min(len(line), j + 11)
                context = line[start:end].replace("\t", " ")
                emojis.append((i, j + 1, char, context))

    return emojis


def scan_file(file_path: Path) -> list[tuple[int, int, str, str]]:
    """Scan a single file for emojis."""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        return find_emojis_in_text(content)
    except (UnicodeDecodeError, PermissionError):
        # Skip files that can't be read as text
        return []


def should_scan_file(file_path: Path, strict_mode: bool = False) -> bool:
    """Determine if a file should be scanned for emojis."""
    # Check file extension
    if file_path.suffix.lower() not in SCANNABLE_EXTENSIONS:
        return False

    # Check if file is in an ignored directory
    for part in file_path.parts:
        if part in IGNORE_DIRS:
            return False

    # Check if file is exempt from emoji scanning (unless in strict mode)
    if not strict_mode:
        relative_path = str(file_path)
        if relative_path.startswith("./"):
            relative_path = relative_path[2:]
        elif relative_path.startswith("/"):
            # Try to make it relative to current directory
            try:
                relative_path = str(file_path.relative_to(Path.cwd()))
            except ValueError:
                pass

        if relative_path in EXEMPT_FILES or file_path.name in EXEMPT_FILES:
            return False

    return True


def scan_directory(directory: Path, strict_mode: bool = False) -> dict:
    """Scan all appropriate files in a directory for emojis."""
    results = {}

    for file_path in directory.rglob("*"):
        if file_path.is_file() and should_scan_file(file_path, strict_mode):
            emojis = scan_file(file_path)
            if emojis:
                results[file_path] = emojis

    return results


def format_results(results: dict) -> str:
    """Format scan results for display."""
    if not results:
        return "✅ No emojis found in scanned files."

    output = []
    total_emojis = 0

    output.append("❌ Emojis found in the following files:")
    output.append("")

    for file_path, emojis in results.items():
        output.append(f"📁 {file_path}:")
        for line_num, col_num, emoji, context in emojis:
            output.append(
                f"  Line {line_num}, Column {col_num}: '{emoji}' in '{context}'"
            )
            total_emojis += 1
        output.append("")

    output.append(f"Total emojis found: {total_emojis}")
    output.append("")
    output.append("Please remove emojis from your source code.")
    output.append("Emojis can cause issues in certain environments and")
    output.append("may not be appropriate for production code.")

    return "\n".join(output)


def main() -> int:
    """Main function to run the emoji scanner."""
    # Always use strict mode and scan all files
    strict_mode = True
    scan_path_arg = None

    # Parse command line arguments for scan path
    for arg in sys.argv[1:]:
        if not scan_path_arg and not arg.startswith("--"):
            scan_path_arg = arg

    # Determine the root directory to scan
    if scan_path_arg:
        scan_path = Path(scan_path_arg)
    else:
        scan_path = Path.cwd()

    if not scan_path.exists():
        print(f"Error: Path '{scan_path}' does not exist.")
        return 1

    print(f"🔍 Scanning for emojis in: {scan_path} (strict mode)")
    print("")

    if scan_path.is_file():
        if should_scan_file(scan_path, strict_mode):
            emojis = scan_file(scan_path)
            results = {scan_path: emojis} if emojis else {}
        else:
            print(f"File type not supported for scanning: {scan_path}")
            return 0
    else:
        results = scan_directory(scan_path, strict_mode)

    output = format_results(results)
    print(output)

    # Return exit code 1 if emojis were found, 0 otherwise
    return 1 if results else 0


if __name__ == "__main__":
    sys.exit(main())
