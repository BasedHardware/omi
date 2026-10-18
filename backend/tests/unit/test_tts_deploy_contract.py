from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'


def _env_entries(path):
    document = yaml.safe_load(path.read_text(encoding='utf-8'))
    return {entry['name']: entry for entry in document['env']}


def test_backend_listen_receives_gemini_key_and_default_provider():
    for environment in ('dev', 'prod'):
        entries = _env_entries(BACKEND / 'charts/backend-listen' / f'{environment}_omi_backend_listen_values.yaml')
        assert entries['TTS_PROVIDER']['value'] == 'gemini'
        assert entries['GEMINI_API_KEY']['valueFrom']['secretKeyRef'] == {
            'name': f'{environment}-omi-backend-secrets',
            'key': 'GEMINI_API_KEY',
        }
        assert entries['ELEVENLABS_API_KEY']['valueFrom']['secretKeyRef'] == {
            'name': f'{environment}-omi-backend-secrets',
            'key': 'ELEVENLABS_API_KEY',
        }


def test_backend_secret_sync_keeps_mobile_legacy_rollback_usable():
    for environment in ('dev', 'prod'):
        values = yaml.safe_load(
            (BACKEND / 'charts/backend-secrets' / f'{environment}_omi_backend_secrets_values.yaml').read_text(
                encoding='utf-8'
            )
        )
        secret_map = {entry['secretKey']: entry['remoteKey'] for entry in values['externalSecret']['secretKeys']}
        assert secret_map['ELEVENLABS_API_KEY'] == 'DESKTOP_ELEVENLABS_API_KEY'


def test_desktop_cloud_run_receives_existing_gemini_secret_and_provider_switch():
    dev = (ROOT / '.github/workflows/desktop_backend_auto_dev.yml').read_text(encoding='utf-8')
    prod = (ROOT / '.github/workflows/desktop_backend_prod.yml').read_text(encoding='utf-8')
    assert 'TTS_PROVIDER=gemini' in dev
    assert 'GEMINI_API_KEY=GEMINI_API_KEY:latest' in dev
    assert 'TTS_PROVIDER=gemini' in prod
    assert 'GEMINI_API_KEY=DESKTOP_GEMINI_API_KEY:latest' in prod


def test_runtime_manifest_tracks_gemini_tts_bindings():
    manifest = yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))['environments']
    for environment in ('dev', 'prod'):
        backend_env = manifest[environment]['gke']['backend-listen']['env']
        assert backend_env['TTS_PROVIDER']['value'] == 'gemini'
        assert backend_env['GEMINI_API_KEY']['secret']['key'] == 'GEMINI_API_KEY'
        assert backend_env['ELEVENLABS_API_KEY']['secret']['key'] == 'ELEVENLABS_API_KEY'
        desktop = manifest[environment]['desktop_backend']
        assert desktop['env']['TTS_PROVIDER']['value'] == 'gemini'
    assert manifest['dev']['desktop_backend']['secrets']['GEMINI_API_KEY']['secret'] == 'GEMINI_API_KEY'
    assert manifest['prod']['desktop_backend']['secrets']['GEMINI_API_KEY']['secret'] == 'DESKTOP_GEMINI_API_KEY'


def test_desktop_runtime_image_installs_ffmpeg_for_mp3_contract():
    dockerfile = (BACKEND / 'Dockerfile.desktop_backend').read_text(encoding='utf-8')
    assert 'install --no-install-recommends ffmpeg' in dockerfile
