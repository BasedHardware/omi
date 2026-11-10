"""Shared content-owner and privacy CAS for recovery and scheduler re-drives.

Keep this fence independent of recovery orchestration so worker images can
verify held grants without importing the recovery provider/projection stack.
"""

from typing import Any

from database.batch_pipeline_projection_protocol import ProjectionBlocked, normalized_binding
from database.sync_ledger_ownership import batch_projection_ledger_owner_matches
from utils.sync.capture import chunk_identity


class RecoveryFence:
    def __init__(self, store: Any):
        self.store = store

    def checked(
        self,
        tx,
        segment_id,
        *,
        allow_completed_silence=False,
        allow_completed_speech_redrive=False,
        allow_completed_terminal=False,
        allow_completed_recovery=False,
    ):
        job = tx.get('jobs', segment_id)
        if not job or not job.get('projection_binding'):
            raise ProjectionBlocked('recovery intake binding required')
        binding = normalized_binding(job['projection_binding'])
        ids = set(job.get('conversation_ids') or [])
        ids.add(
            chunk_identity(
                binding.owner_id, binding.source, binding.client_device_id, binding.is_locked, job['capture_at']
            )
        )
        ids.update(value for value in (job.get('conversation_id'), binding.target_conversation_id) if value)
        tx.check_privacy(binding.owner_id, ids, binding.privacy_generation)
        ledger = tx.get('content', f'{binding.owner_id}/{binding.content_id}')
        if (
            job.get('owner_id') != binding.owner_id
            or job.get('privacy_generation') != binding.privacy_generation
            or (job.get('recovery') and job['recovery'].get('privacy_generation') != binding.privacy_generation)
            or segment_id not in binding.segment_ids
            or ledger.get('dispatch_protocol') != 'batch_v1'
            or ledger.get('batch_pipeline')
            != {'protocol_version': 1, 'namespace': self.store.namespace, 'segment_ids': list(binding.segment_ids)}
            or not (
                batch_projection_ledger_owner_matches(ledger, binding.job_id, binding.run_token, binding.run_epoch)
                or (
                    allow_completed_silence
                    and ledger.get('status') == 'completed'
                    and ledger.get('job_id') == binding.job_id
                    and job.get('silence_disposition', {}).get('state') == 'completed'
                    and job.get('result', {}).get('outcome') == 'silence'
                )
                or (
                    allow_completed_speech_redrive
                    and ledger.get('status') == 'completed'
                    and ledger.get('job_id') == binding.job_id
                    and job.get('speech_redrive', {}).get('state') == 'completed'
                    and job.get('result', {}).get('outcome') in {'success', 'no_recoverable_speech', 'silence'}
                )
                or (
                    allow_completed_recovery
                    and ledger.get('status') == 'completed'
                    and ledger.get('job_id') == binding.job_id
                    and job.get('recovery_state') == 'recovered'
                    and bool(job.get('result'))
                )
                or (
                    allow_completed_terminal
                    and ledger.get('status') == 'completed'
                    and ledger.get('job_id') == binding.job_id
                    and job.get('terminal_disposition', {}).get('state') == 'completed'
                    and job.get('result', {}).get('outcome') == job['terminal_disposition'].get('outcome')
                )
            )
        ):
            raise ProjectionBlocked('recovery content owner lost')
        return job, binding
