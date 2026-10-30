#!/usr/bin/env python3
"""Exercise patched pinned native getTextFromWavFile, real WAV parsing and RAII.
Only the heavyweight whisper kernel is fault-injected; no Dart method override.
"""
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse, unquote
from patch_whisper_cleanup import patch

app = Path(__file__).resolve().parents[1]
config = app / '.dart_tool/package_config.json'
pkg = next(p for p in json.loads(config.read_text())['packages'] if p['name'] == 'whisper_flutter_new')
uri = urlparse(pkg['rootUri'])
root = Path(unquote(uri.path)) if uri.scheme == 'file' else (config.parent / pkg['rootUri']).resolve()
with tempfile.TemporaryDirectory(prefix='whisper-cleanup-') as directory:
    temp = Path(directory)
    (temp / 'main.cpp').write_text(patch((root / 'src/main.cpp').read_text()))
    harness = r'''
#include "whisper.cpp/whisper.h"
#include <cassert>
#include <fstream>
#include <dirent.h>
#include <stdexcept>
#include "main.cpp"
static int live = 0;
static int fault = 0;
extern "C" {
struct whisper_context *whisper_init_from_file(const char *path) {
    if (std::string(path) == "bad-model") return nullptr;
    ++live; return reinterpret_cast<whisper_context *>(new char[1]);
}
void whisper_free(struct whisper_context *ctx) { --live; delete[] reinterpret_cast<char *>(ctx); }
int whisper_lang_id(const char *) { return 0; }
struct whisper_full_params whisper_full_default_params(enum whisper_sampling_strategy) { return {}; }
int whisper_full(struct whisper_context *, struct whisper_full_params, const float *, int) {
    if (fault == 2) throw std::runtime_error("injected inference exception");
    return fault;
}
int whisper_full_n_segments(struct whisper_context *) { return 0; }
const char *whisper_full_get_segment_text(struct whisper_context *, int) { return ""; }
int64_t whisper_full_get_segment_t0(struct whisper_context *, int) { return 0; }
int64_t whisper_full_get_segment_t1(struct whisper_context *, int) { return 0; }
}
int descriptors() {
    DIR *d = opendir("/dev/fd"); int n = 0;
    while (readdir(d)) ++n;
    closedir(d); return n;
}
void wav(const char *path, int rate, int channels = 1, int bits = 16) {
    std::ofstream f(path, std::ios::binary);
    auto u16 = [&](uint16_t x) { f.write(reinterpret_cast<char *>(&x), 2); };
    auto u32 = [&](uint32_t x) { f.write(reinterpret_cast<char *>(&x), 4); };
    f.write("RIFF",4); u32(36+320); f.write("WAVEfmt ",8); u32(16); u16(1);
    u16(channels); u32(rate); u32(rate*channels*bits/8); u16(channels*bits/8); u16(bits);
    f.write("data",4); u32(320); char pcm[320] = {}; f.write(pcm,320);
}
int main() {
    wav("pcm8.wav",8000); wav("channels.wav",16000,3); wav("bits.wav",16000,1,8); wav("valid.wav",16000);
    auto request = [](const char *file, const char *model = "model") {
        whisper_params p; p.audio = file; p.model = model; p.no_timestamps = true;
        return transcribe(json{{"model",model},{"audio",file},{"language","en"},{"threads",1},{"is_verbose",false},{"is_translate",false},{"is_special_tokens",false},{"is_no_timestamps",true},{"split_on_word",false}});
    };
    const int before = descriptors();
    for (int i=0; i<100; ++i) {
        for (const char *file : {"pcm8.wav","channels.wav","bits.wav","missing.wav"}) {
            auto result = request(file);
            assert(result["@type"] == "error");
            assert(result["message"].get<std::string>().find("OMI_STT_PERMANENT_INPUT:") == 0);
            assert(live == 0 && descriptors() == before);
        }
        fault = 1; assert(request("valid.wav")["@type"] == "error"); assert(live == 0);
        fault = 2;
        try { request("valid.wav"); assert(false); } catch (const std::runtime_error &) {}
        assert(live == 0 && descriptors() == before);
    }
    fault = 0; assert(request("valid.wav")["text"] == ""); assert(live == 0);
    assert(request("valid.wav","bad-model")["@type"] == "error"); assert(live == 0);
    assert(descriptors() == before);
}
'''
    (temp / 'test.cpp').write_text(harness)
    subprocess.run(['clang++', '-std=c++20', '-fsanitize=address,undefined', '-I'+str(root/'src'), '-I'+str(temp),
                    str(temp/'test.cpp'), '-o', str(temp/'test')], check=True)
    subprocess.run([str(temp/'test')], cwd=temp, check=True)
print('Pinned native error cleanup passed: 600 error/exception paths, no live contexts or leaked WAV handles')
