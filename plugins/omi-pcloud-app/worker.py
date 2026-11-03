"""Durable, leased per-conversation backup execution. No UID-only audio state."""

import hashlib
import os
import tempfile
import time
from urllib.parse import quote, urlsplit

import requests

from pcloud_client import PCloudClient

MAX_AUDIO_BYTES = 512 * 1024 * 1024


class BackupFailure(Exception):
    """Contains only fixed, user-safe recovery text, never provider bodies."""


class BackupCanceled(Exception):
    pass


def active_connection(store, uid, job):
    connection = store.get('connection', uid)
    if not connection or connection['status'] != 'active' or connection['generation'] != job['generation']:
        raise BackupCanceled()
    return connection


def access_url(job):
    base = os.getenv('OMI_API_BASE_URL', 'https://api.omi.me').rstrip('/')
    parts = urlsplit(base)
    if (
        parts.scheme != 'https'
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise BackupFailure('The Omi audio service address is not configured correctly. Contact the app administrator.')
    app_id = quote(os.environ['OMI_PLUGIN_APP_ID'], safe='')
    conversation_id = quote(job['conversation_id'], safe='')
    return f'{base}/v1/apps/{app_id}/backup-audio/{conversation_id}'


def confirm_access(job):
    try:
        response = requests.head(
            access_url(job),
            headers={'Authorization': f'Bearer {job["authorization_token"]}'},
            timeout=(5, 15),
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise BackupFailure(
                'Omi could not confirm access to this conversation. Check that the backup app is enabled, then retry.'
            )
    except requests.RequestException:
        raise BackupFailure(
            'Could not confirm backup access with Omi. No new file was sent; retry when Omi is reachable.'
        )


def audio_manifest(uid, job):
    try:
        response = requests.get(
            access_url(job),
            headers={'Authorization': f'Bearer {job["audio_token"]}'},
            timeout=(5, 20),
            allow_redirects=False,
        )
        response.raise_for_status()
        manifest = response.json()
        files = manifest.get('audio_files')
        if not isinstance(files, list) or not files:
            raise BackupFailure(
                'Omi has no saved audio for this conversation. Summary and transcript backups are unaffected.'
            )
        if any(
            not isinstance(item, dict) or item.get('status') != 'cached' or not item.get('signed_url') for item in files
        ):
            raise BackupFailure(
                'Saved audio is not ready or is no longer available in Omi. Retry after checking playback in Omi.'
            )
        return files
    except (requests.RequestException, ValueError, AttributeError):
        raise BackupFailure(
            'Could not read saved audio from Omi. Check that the app is enabled, then retry the backup.'
        )


def audio_payload(url):
    """Only canonical GCS links, no redirects; spool rather than buffering a meeting in RAM."""
    parts = urlsplit(url)
    host = parts.hostname or ''
    if (
        parts.scheme != 'https'
        or parts.port not in (None, 443)
        or parts.username
        or parts.password
        or parts.fragment
        or not (host == 'storage.googleapis.com' or host.endswith('.storage.googleapis.com'))
    ):
        raise BackupFailure('Omi returned an unsupported audio download address. Contact the app administrator.')
    handle = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
    try:
        with requests.get(url, stream=True, timeout=(5, 30), allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise BackupFailure('Audio download was redirected or incomplete. Retry the backup.')
            length = response.headers.get('Content-Length')
            if length and int(length) > MAX_AUDIO_BYTES:
                raise BackupFailure('This audio file exceeds the 512 MB backup limit. Export it manually from Omi.')
            total = 0
            started = time.monotonic()
            for chunk in response.iter_content(1024 * 1024):
                if time.monotonic() - started > 120:
                    raise BackupFailure('Audio download took too long. Retry when the connection is stable.')
                total += len(chunk)
                if total > MAX_AUDIO_BYTES:
                    raise BackupFailure('This audio file exceeds the 512 MB backup limit. Export it manually from Omi.')
                handle.write(chunk)
            if not total or (length and int(length) != total):
                raise BackupFailure('Audio download was incomplete. Retry the backup.')
        handle.seek(0)
        return handle
    except BaseException:
        handle.close()
        raise


def run_next_job(store) -> bool:
    claimed = store.claim()
    if claimed is None:
        return False
    identity, uid, lease, job = claimed
    job['attempt'] += 1

    def checkpoint():
        store.settle(identity, uid, lease, job, 'running', delay=300)

    def upload(filename, content):
        # Settings and disconnect use this same lock. Once they return, no later
        # file can be sent with the previous consent/connection generation.
        with store.account_lock(uid):
            connection = active_connection(store, uid, job)
            settings = store.settings(uid)
            option = (
                'save_audio'
                if filename.startswith('audio-')
                else ('save_transcript' if filename == 'transcript.md' else 'save_summary')
            )
            if not settings[option]:
                return
            if job['path'] != f'/{settings["folder_name"]}/{identity}':
                raise BackupFailure('The backup folder changed while this backup was running. Retry to save it there.')
            client = PCloudClient(connection['access_token'], connection['location_id'])
            confirm_access(job)
            checkpoint()
            folder, error = client.ensure_folder(job['path'])
            if error or folder is None:
                raise BackupFailure(
                    'Could not create the pCloud folder. Check your storage space and connection, then retry.'
                )
            result, error = client.upload_file(folder, filename, content, overwrite=True)
            if error or result is None:
                raise BackupFailure(
                    'pCloud did not confirm this file upload. Check your storage space and connection, then retry.'
                )
            job['uploaded'].append(filename)
            checkpoint()

    try:
        with store.account_lock(uid):
            active_connection(store, uid, job)
            # A backup that has not finished follows the destination the user
            # chose since it was queued, and lands there complete.
            destination = f'/{store.settings(uid)["folder_name"]}/{identity}'
            if job['path'] != destination:
                job.update(path=destination, uploaded=[])
                checkpoint()
        for filename, text in job['files'].items():
            if filename not in job['uploaded']:
                upload(filename, text.encode('utf-8'))
        if job.get('audio_token'):
            with store.account_lock(uid):
                active_connection(store, uid, job)
                enabled = store.settings(uid)['save_audio']
            if enabled:
                for entry in audio_manifest(uid, job):
                    extension = 'mp3' if entry.get('content_type') == 'audio/mpeg' else 'wav'
                    audio_id = str(entry['id'])
                    audio_identity = hashlib.sha256(audio_id.encode()).hexdigest()
                    filename = f'audio-{PCloudClient.sanitize_path(audio_id)[:24]}-{audio_identity}.{extension}'
                    if filename not in job['uploaded']:
                        checkpoint()
                        with audio_payload(entry['signed_url']) as content:
                            upload(filename, content)
        job.update(error=None, files={}, audio_token=None, authorization_token=None)
        with store.account_lock(uid):
            active_connection(store, uid, job)
            store.settle(identity, uid, lease, job, 'completed')
    except BackupCanceled:
        # Disconnect may already have canceled and scrubbed this job/lease.
        try:
            store.settle(
                identity,
                uid,
                lease,
                {'id': identity, 'uploaded': [], 'error': 'Backup canceled because the connection changed.'},
                'canceled',
            )
        except RuntimeError:
            pass
    except Exception as error:
        job['error'] = (
            str(error)
            if isinstance(error, BackupFailure)
            else 'Backup could not finish. Retry, or contact support if it continues.'
        )
        delay = min(3600, 30 * 2 ** min(job['attempt'], 6))
        try:
            store.settle(identity, uid, lease, job, 'pending' if job['attempt'] < 5 else 'failed', delay=delay)
        except RuntimeError:
            pass
    return True
