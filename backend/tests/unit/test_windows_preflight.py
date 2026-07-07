from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_windows_preflight_points_to_existing_dependency_sync_script():
    script = (BACKEND_DIR / 'test-preflight.ps1').read_text(encoding='utf-8')

    assert 'sync-python-deps.ps1' not in script
    assert 'bash ./scripts/sync-python-deps.sh' in script
    assert (BACKEND_DIR / 'scripts' / 'sync-python-deps.sh').is_file()
