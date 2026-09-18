from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "dev-harness" / "generate-app-env.sh"


def test_generate_app_env_is_non_destructive() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    invocations = [
        line
        for line in text.splitlines()
        if "flutter" in line and "build_runner" in line and not line.lstrip().startswith("#")
    ]
    assert invocations, "expected a build_runner invocation"
    for line in invocations:
        assert "--delete-conflicting-outputs" not in line
        assert "--build-filter" not in line


def test_generate_app_env_restores_tracked_files_deleted_by_build_runner(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    app = repo / "app" / "lib" / "env"
    app.mkdir(parents=True)
    tracked = repo / "app" / "lib" / "utils" / "manifest"
    tracked.mkdir(parents=True)
    (tracked / "manifest.g.dart").write_text("// tracked\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "app/lib/utils/manifest/manifest.g.dart"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "track"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    flutter = bin_dir / "flutter"
    flutter.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "# Invoked with cwd=app (generate-app-env.sh cds there).\n"
        "rm -f lib/utils/manifest/manifest.g.dart\n"
        "mkdir -p lib/env\n"
        "echo '// generated' > lib/env/dev_env.g.dart\n"
        "echo '// generated' > lib/env/prod_env.g.dart\n",
        encoding="utf-8",
    )
    flutter.chmod(flutter.stat().st_mode | stat.S_IXUSR)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    script = SCRIPT.read_text(encoding="utf-8")
    local = repo / "scripts" / "dev-harness"
    local.mkdir(parents=True)
    (local / "generate-app-env.sh").write_text(script, encoding="utf-8")
    (local / "generate-app-env.sh").chmod(0o755)

    completed = subprocess.run(
        ["bash", str(local / "generate-app-env.sh")],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (tracked / "manifest.g.dart").is_file(), "tracked manifest.g.dart must survive"
    assert (tracked / "manifest.g.dart").read_text(encoding="utf-8") == "// tracked\n"
    assert (app / "dev_env.g.dart").is_file()
