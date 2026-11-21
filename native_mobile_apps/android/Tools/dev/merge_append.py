#!/usr/bin/env python3
"""Resolve append-only merge conflicts (both sides added lines to the same block) by keeping both.

For the `APIClient.kt` delegation list it also fixes the commas: the HEAD side's last entry ends a
list (`... ,` / `... {`) that the other side continues. Usage: merge_append.py <branch-name>
"""
import re
import subprocess
import sys

branch = sys.argv[1]
files = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"]).decode().split()
pattern = re.compile(r"<<<<<<< HEAD\n(.*?)=======\n(.*?)>>>>>>> " + re.escape(branch) + r"\n", re.S)


def join(head: str, other: str) -> str:
    if head.rstrip().endswith(" {"):  # class delegation list closes the body on HEAD's last line
        return head.rstrip()[:-2] + ",\n" + other
    last = head.rstrip().splitlines()[-1] if head.strip() else ""
    if re.search(r"API$", last.strip()) and not last.strip().startswith("import"):  # interface list
        return head.rstrip() + ",\n" + other
    return head + other


for path in files:
    text = open(path).read()
    text = pattern.sub(lambda m: join(m.group(1), m.group(2)), text)
    open(path, "w").write(text)
    left = text.count("<<<<<<<")
    print(f"{path}: {'resolved' if left == 0 else f'{left} conflicts left'}")
