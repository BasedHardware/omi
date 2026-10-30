#!/usr/bin/env python3
"""Fail-closed, idempotent native cleanup patch for pinned whisper_flutter_new.

Like the foreground-task patch, invoked by native build setup. No dependency
revision change: RAII owns both resources across errors and C++ exceptions.
"""
from pathlib import Path
import sys
import os
import tempfile

MARKER = 'OMI_WHISPER_RESOURCE_GUARDS_V1'

def patch(source: str) -> str:
    if MARKER in source:
        return source
    replacements = {
        'json transcribe(json jsonBody) noexcept': 'json transcribe(json jsonBody)',
        '#include <cstdio>': '#include <cstdio>\n#include <memory>\n// ' + MARKER,
        '    struct whisper_context *ctx = whisper_init_from_file(params.model.c_str());': '''    std::unique_ptr<whisper_context, decltype(&whisper_free)> context(
        whisper_init_from_file(params.model.c_str()), &whisper_free);
    auto *ctx = context.get();
    if (!ctx) {
        jsonResult["@type"] = "error";
        jsonResult["message"] = "OMI_STT_MODEL_UNAVAILABLE: model could not be loaded";
        return jsonResult;
    }''',
        '        if (wav.channels != 1 && wav.channels != 2)': '''        auto wav_cleanup = [&wav](drwav *) { drwav_uninit(&wav); };
        std::unique_ptr<drwav, decltype(wav_cleanup)> wav_guard(&wav, wav_cleanup);
        if (wav.channels != 1 && wav.channels != 2)''',
        '        drwav_uninit(&wav);': '',
        '    whisper_free(ctx);': '',
        ' failed to open WAV file ': 'OMI_STT_PERMANENT_INPUT: failed to open WAV file',
        'must be mono or stereo': 'OMI_STT_PERMANENT_INPUT: must be mono or stereo',
        'WAV file  must be 16 kHz': 'OMI_STT_PERMANENT_INPUT: WAV file must be 16 kHz',
        'WAV file  must be 16 bit': 'OMI_STT_PERMANENT_INPUT: WAV file must be 16 bit',
        'error: unknown language = ': 'OMI_STT_PERMANENT_INPUT: unknown language = ',
        'failed to process audio': 'OMI_STT_RETRYABLE: failed to process audio',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError(f'Pinned Whisper source drift: expected exactly one {old!r}')
        source = source.replace(old, new)
    return source

if __name__ == '__main__':
    for arg in sys.argv[1:]:
        path = Path(arg)
        old = path.read_text()
        new = patch(old)
        if new != old:
            with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as output:
                output.write(new)
                temporary = output.name
            os.chmod(temporary, path.stat().st_mode)
            os.replace(temporary, path)
        print(f'Whisper cleanup verified: {path.name}')
