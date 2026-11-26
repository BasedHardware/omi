"""What each stand-in did in one scenario run, in words, from that run's own counters (stdlib only).

``scenario/ops.py`` counts every stand-in it takes (``stand_ins``) and, for the ones that write words, where
those words came from (``stand_in_sources``: ``scripted`` for speech lines in the scenario, else the STT
cassette's source, ``synthetic`` / ``local`` / ``vendor``). ``scenario/audio.py`` reports, per
``audio_file`` recording, the lane driver's product steps and stand-ins (``audio.recordings``).

:func:`stand_in_notes` and :func:`audio_steps` turn those into the lines ``result.json``, ``verdict.json``,
the text report and the web view show, so a line never claims a step the run did not take. A run directory
written before these fields existed gets notes rebuilt from its counters; without ``stand_in_sources`` the
word source is read from ``audio.recordings`` (any audio recording means the words were not all scripted).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

CAPTURE_CLOSE = 'capture_close'
ADMISSION = 'record_admission'
PROJECTION = 'batch_projection'
SYNC = 'sync_intake'
OUTLINE = 'outline_model'

# Audio-to-words steps, by lane driver step name (lanes/batch.py, lanes/sync.py): the plain name a reader
# sees. Anything not listed is shown as its step name.
STEP_NAMES = {
    'decode_pcm16_wav': 'decode (decode_pcm16_wav)',
    'decode_files_to_wav': 'decode (decode_files_to_wav)',
    'PipelineWorker.process_batch': 'windows and packing (PipelineWorker.process_batch)',
    'projection_segments': 'segments (projection_segments)',
    'retrieve_vad_segments': 'speech windows (retrieve_vad_segments)',
    'merge_and_cap_vad_segments': 'window merge and cap (merge_and_cap_vad_segments)',
    'postprocess_words': 'segments (postprocess_words)',
    'first_word_offset': 'word offsets (first_word_offset)',
    'unit_cut': 'unit cut (one unit over the file)',
    'dispatch_admission(allow)': 'dispatch admission (allowed)',
    'vad(local silero, prod: gpu pyannote)': 'local Silero VAD (production: GPU pyannote)',
    'vad_model(local silero)': 'local Silero VAD',
    'asr(cassette)': 'cassette words',
    'stt(cassette)': 'cassette words',
    'diarization(cassette)': 'cassette speaker labels',
    'conversation_targeting(baseline clock)': 'conversation targeting (baseline clock)',
}


def _sources(result: Mapping[str, Any], name: str) -> dict[str, int]:
    given = (result.get('stand_in_sources') or {}).get(name)
    if given:
        return {str(k): int(v) for k, v in given.items()}
    audio = {row.get('source') for row in (result.get('audio') or {}).get('recordings') or []}
    count = int((result.get('stand_ins') or {}).get(name) or 0)
    if not audio:
        return {'scripted': count} if count else {}
    return {'not recorded': count} if count else {}


def _words_from(sources: Mapping[str, int], *, lane: str) -> str:
    parts = []
    for source in sorted(sources):
        if source == 'scripted':
            parts.append("the scenario's scripted lines")
        elif source == 'not recorded':
            parts.append('scripted lines or cassette words (this run predates per-source counts)')
        else:
            via = (
                'the real PipelineWorker and projection_segments'
                if lane == 'batch'
                else 'the real retrieve_vad_segments and postprocess_words'
            )
            parts.append(f'the words of the {source} STT cassette for its audio, through {via}')
    return ' and '.join(parts) if parts else 'no words'


def stand_in_notes(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """``[{"name", "count", "text"}]`` for every stand-in this run took, plus the outline model; nothing for a
    run that never reached the events (no ``stand_ins`` counters, e.g. an error before the driver)."""
    if 'stand_ins' not in result:
        return []
    counts = {str(k): int(v) for k, v in (result.get('stand_ins') or {}).items()}
    out = []
    for name, count in counts.items():
        sources = _sources(result, name)
        if name == CAPTURE_CLOSE:
            text = (
                'A Finish that landed while the capture was in progress was stored at the seal the way the '
                "finalization job's capture close stores it (status completed and the manual-end request in one "
                'write); the job, its lease and its outbox did not run.'
            )
        elif name == ADMISSION:
            text = (
                'Batch record admission (audio listing, units, staging, intake) did not run; the manual-finish '
                'hook got one unit over the whole recording (one retained reference, read as silence), a privacy '
                'check that allows, and the funding gate open. The fast-finish STT returned '
                f'{_words_from(sources, lane="batch")}, per chunk on the chunked path, with no language probe.'
            )
        elif name == PROJECTION:
            text = (
                'The batch transcript landed through the live transcript writer (update_conversation_segments) '
                'and stamped record_projection_revision; the projection transaction (replace_record, its '
                f'manual-end promotion, receipts) did not run. Its segments were {_words_from(sources, lane="batch")}.'
            )
        elif name == SYNC:
            text = (
                'A device-sync fragment was written as a completed recording and woken as the projection would; '
                'the /v2/sync-local-files intake and its batch job did not run. Its segments were '
                f'{_words_from(sources, lane="sync")}.'
            )
        else:
            text = ''
        out.append({'name': name, 'count': count, 'text': text})
    out.append(
        {
            'name': OUTLINE,
            'count': None,
            'text': "The outline and every other LLM answer came from the lab's fake gateway (one conversation "
            'per stretch; a new one at "switching topics"); no model ran.',
        }
    )
    return out


def audio_steps(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Per ``audio_file`` recording: the audio-to-words steps that ran as product code and the stand-ins."""
    out = []
    for row in (result.get('audio') or {}).get('recordings') or []:
        product = [STEP_NAMES.get(step, step) for step in row.get('product') or []]
        stand_ins = []
        for step in row.get('simulated') or []:
            if str(step).startswith('speaker_identification'):
                stand_ins.append('no speaker identification (no voiceprints)')
            elif str(step).startswith('sync intake'):
                continue  # the sync_intake stand-in note says this
            else:
                stand_ins.append(STEP_NAMES.get(step, step))
        source = row.get('source')
        cassette = f'{source} cassette' + (
            f' ({row.get("provider")}/{row.get("model")})' if row.get('provider') else ''
        )
        text = (
            f'Audio {row.get("label")} ({row.get("lane")} lane, {row.get("audio_file")}): product code: '
            + (', '.join(product) or 'none')
            + '; stand-ins: '
            + ', '.join(s.replace('cassette words', f'cassette words ({cassette})') for s in stand_ins)
            + '.'
        )
        out.append(
            {
                'label': row.get('label'),
                'lane': row.get('lane'),
                'source': source,
                'product': product,
                'stand_ins': stand_ins,
                'text': text,
            }
        )
    return out


def lines(result: Mapping[str, Any]) -> Sequence[str]:
    """The text report's lines: one per stand-in, one per audio recording."""
    rows = result.get('stand_in_notes') or stand_in_notes(result)
    out = [f'{row["name"]}' + (f' x{row["count"]}' if row.get('count') else '') + f': {row["text"]}' for row in rows]
    out += [f'audio to words: {row["text"]}' for row in result.get('audio_steps') or audio_steps(result)]
    return out
