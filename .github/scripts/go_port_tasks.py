"""Read GitHub PR file records from stdin and emit port task drafts as JSON."""

import argparse
import json
from pathlib import Path
import re
import sys

import yaml


PORT_MAP = Path(__file__).resolve().parents[2] / "backend-go/docs/port-map.yaml"


def load_port_map(path):
    families = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(families, dict) or not families:
        raise ValueError("port map must be a nonempty mapping from families to Python paths")
    for family, paths in families.items():
        if not isinstance(family, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", family):
            raise ValueError(f"invalid family name: {family!r}")
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"{family} must list at least one Python path")
        if any(not isinstance(p, str) or not re.fullmatch(r"backend/(?:[\w-]+/)*[\w-]+\.py", p) for p in paths):
            raise ValueError(f"{family} must list exact repository-relative backend Python paths")
    return families


def changed_paths(files, expected_count=None):
    if not isinstance(files, list):
        raise ValueError("expected a JSON array of GitHub PR file records")
    if expected_count is not None and len(files) != expected_count:
        raise ValueError(f"expected {expected_count} PR files, received {len(files)}")
    paths = set()
    filenames = set()
    for file in files:
        if not isinstance(file, dict):
            raise ValueError("each PR file record must be an object")
        for field in ("filename", "previous_filename"):
            if field == "previous_filename" and field not in file:
                continue
            path = file.get(field)
            if not isinstance(path, str) or not path:
                raise ValueError(f"{field} must be a nonempty string")
            paths.add(path)
        filenames.add(file["filename"])
    if expected_count is not None and len(filenames) != expected_count:
        raise ValueError(f"expected {expected_count} distinct PR filenames, received {len(filenames)}")
    return paths


def port_tasks(pr_number, families, paths):
    source = f"https://github.com/BasedHardware/omi/pull/{pr_number}"
    tasks = []
    for family, python_paths in sorted(families.items()):
        matched = sorted(paths.intersection(python_paths))
        if not matched:
            continue
        files = ", ".join(f"`{path}`" for path in matched)
        tasks.append(
            {
                "family": family,
                "title": f"Port Python PR #{pr_number} to Go {family}",
                "body": (
                    f"Python PR [#{pr_number}]({source}) changed {files}. Review the merged diff and "
                    f"port any behavior changes to the Go {family} family under `backend-go/`. "
                    "Add or update parity coverage for the changed behavior, or record why the Go port needs no change."
                ),
                "matched_paths": matched,
            }
        )
    return tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", required=True, type=int, help="Merged BasedHardware/omi PR number")
    parser.add_argument("--changed-files", type=int, help="Expected file count from the GitHub PR metadata")
    args = parser.parse_args()
    if args.pr < 1:
        parser.error("--pr must be positive")
    if args.changed_files is not None and args.changed_files < 0:
        parser.error("--changed-files must be nonnegative")
    try:
        families = load_port_map(PORT_MAP)
        paths = changed_paths(json.load(sys.stdin), args.changed_files)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(2, f"{parser.prog}: {error}\n")
    print(json.dumps(port_tasks(args.pr, families, paths), indent=2))


if __name__ == "__main__":
    main()
