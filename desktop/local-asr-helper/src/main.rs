use serde::{Deserialize, Serialize};
use std::env;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const SAMPLE_RATE: u32 = 16_000;
const CHANNELS: u8 = 1;

#[derive(Debug, Deserialize, Serialize, Clone, PartialEq)]
#[serde(rename_all = "snake_case")]
struct TranscriptionRequest {
    request_id: String,
    audio_path: String,
    language: String,
    sample_rate: u32,
    channels: u8,
    engine: LocalEngine,
    model: LocalModel,
    fixture_segments: Option<Vec<TranscriptSegment>>,
}

#[derive(Debug, Deserialize, Serialize, Clone, Copy, PartialEq)]
#[serde(rename_all = "kebab-case")]
enum LocalEngine {
    MlxWhisper,
    FasterWhisper,
}

impl LocalEngine {
    fn as_str(self) -> &'static str {
        match self {
            Self::MlxWhisper => "mlx-whisper",
            Self::FasterWhisper => "faster-whisper",
        }
    }
}

#[derive(Debug, Deserialize, Serialize, Clone, Copy, PartialEq)]
#[serde(rename_all = "snake_case")]
enum LocalModel {
    Tiny,
    Base,
    Small,
    Medium,
    LargeV3Turbo,
}

impl LocalModel {
    fn as_str(self) -> &'static str {
        match self {
            Self::Tiny => "tiny",
            Self::Base => "base",
            Self::Small => "small",
            Self::Medium => "medium",
            Self::LargeV3Turbo => "large_v3_turbo",
        }
    }
}

#[derive(Debug, Deserialize, Serialize, Clone, PartialEq)]
struct TranscriptSegment {
    id: Option<String>,
    speaker: Option<i32>,
    text: String,
    start: f64,
    end: f64,
}

#[derive(Debug, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
struct TranscriptionResponse {
    request_id: String,
    engine: LocalEngine,
    model: LocalModel,
    language: String,
    segments: Vec<TranscriptSegment>,
    fixture: bool,
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
struct CapabilityResponse {
    engines: Vec<EngineCapability>,
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
struct EngineCapability {
    engine: LocalEngine,
    available: bool,
    reason: Option<String>,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    if env::args().any(|arg| arg == "--capabilities") {
        let response = CapabilityResponse {
            engines: vec![
                probe_engine(LocalEngine::MlxWhisper),
                probe_engine(LocalEngine::FasterWhisper),
            ],
        };
        println!(
            "{}",
            serde_json::to_string(&response).map_err(|error| error.to_string())?
        );
        return Ok(());
    }

    let request = read_request()?;
    let segments = match request.fixture_segments.clone() {
        Some(segments) => {
            let response = TranscriptionResponse {
                request_id: request.request_id,
                engine: request.engine,
                model: request.model,
                language: request.language,
                segments,
                fixture: true,
            };
            println!(
                "{}",
                serde_json::to_string(&response).map_err(|error| error.to_string())?
            );
            return Ok(());
        }
        None => transcribe(&request)?,
    };

    let response = TranscriptionResponse {
        request_id: request.request_id,
        engine: request.engine,
        model: request.model,
        language: request.language,
        segments,
        fixture: false,
    };
    println!(
        "{}",
        serde_json::to_string(&response).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn read_request() -> Result<TranscriptionRequest, String> {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|error| format!("failed to read stdin: {error}"))?;
    serde_json::from_str(&input).map_err(|error| format!("invalid request json: {error}"))
}

fn transcribe(request: &TranscriptionRequest) -> Result<Vec<TranscriptSegment>, String> {
    if request.sample_rate != SAMPLE_RATE || request.channels != CHANNELS {
        return Err(format!(
            "local ASR expects {SAMPLE_RATE} Hz mono PCM, got {} Hz with {} channel(s)",
            request.sample_rate, request.channels
        ));
    }

    let capability = probe_engine(request.engine);
    if !capability.available {
        return Err(format!(
            "{} is unavailable: {}",
            request.engine.as_str(),
            capability
                .reason
                .unwrap_or_else(|| "capability probe failed".to_string())
        ));
    }

    let audio_path = Path::new(&request.audio_path);
    if !audio_path.is_file() {
        return Err(format!("audio file does not exist: {}", request.audio_path));
    }

    let wav_path = write_wav_copy(audio_path, &request.request_id)?;
    let result = transcribe_with_python(request, &wav_path);
    let _ = fs::remove_file(&wav_path);
    result
}

fn write_wav_copy(pcm_path: &Path, request_id: &str) -> Result<PathBuf, String> {
    let pcm = fs::read(pcm_path).map_err(|error| format!("failed to read PCM audio: {error}"))?;
    if pcm.len() % 2 != 0 {
        return Err("PCM audio must be signed 16-bit little-endian samples".to_string());
    }

    let path = env::temp_dir().join(format!("omi-local-asr-{request_id}.wav"));
    let mut file =
        File::create(&path).map_err(|error| format!("failed to create WAV file: {error}"))?;
    write_wav_header(&mut file, pcm.len() as u32)?;
    file.write_all(&pcm)
        .map_err(|error| format!("failed to write WAV audio: {error}"))?;
    Ok(path)
}

fn write_wav_header(file: &mut File, data_len: u32) -> Result<(), String> {
    let byte_rate = SAMPLE_RATE * CHANNELS as u32 * 2;
    let block_align = CHANNELS as u16 * 2;
    file.write_all(b"RIFF").map_err(|error| error.to_string())?;
    file.write_all(&(36 + data_len).to_le_bytes())
        .map_err(|error| error.to_string())?;
    file.write_all(b"WAVEfmt ")
        .map_err(|error| error.to_string())?;
    file.write_all(&16u32.to_le_bytes())
        .map_err(|error| error.to_string())?;
    file.write_all(&1u16.to_le_bytes())
        .map_err(|error| error.to_string())?;
    file.write_all(&(CHANNELS as u16).to_le_bytes())
        .map_err(|error| error.to_string())?;
    file.write_all(&SAMPLE_RATE.to_le_bytes())
        .map_err(|error| error.to_string())?;
    file.write_all(&byte_rate.to_le_bytes())
        .map_err(|error| error.to_string())?;
    file.write_all(&block_align.to_le_bytes())
        .map_err(|error| error.to_string())?;
    file.write_all(&16u16.to_le_bytes())
        .map_err(|error| error.to_string())?;
    file.write_all(b"data").map_err(|error| error.to_string())?;
    file.write_all(&data_len.to_le_bytes())
        .map_err(|error| error.to_string())
}

fn transcribe_with_python(
    request: &TranscriptionRequest,
    wav_path: &Path,
) -> Result<Vec<TranscriptSegment>, String> {
    let model = model_argument(request.engine, request.model)?;
    let output = Command::new(python_executable())
        .arg("-c")
        .arg(PYTHON_TRANSCRIBE)
        .arg(request.engine.as_str())
        .arg(model)
        .arg(wav_path)
        .arg(&request.language)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .map_err(|error| format!("failed to start Python ASR adapter: {error}"))?;

    if !output.status.success() {
        return Err(format!(
            "Python ASR adapter failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }

    serde_json::from_slice(&output.stdout).map_err(|error| {
        format!(
            "invalid Python ASR adapter response: {error}: {}",
            String::from_utf8_lossy(&output.stdout).trim()
        )
    })
}

fn probe_engine(engine: LocalEngine) -> EngineCapability {
    if engine == LocalEngine::MlxWhisper && !is_native_apple_silicon() {
        return EngineCapability {
            engine,
            available: false,
            reason: Some("MLX Whisper requires native Apple Silicon".to_string()),
        };
    }

    let output = Command::new(python_executable())
        .arg("-c")
        .arg(PYTHON_PROBE)
        .arg(engine.as_str())
        .arg(model_argument_for_probe(engine).unwrap_or_default())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output();

    match output {
        Ok(output) if output.status.success() => EngineCapability {
            engine,
            available: true,
            reason: None,
        },
        Ok(output) => EngineCapability {
            engine,
            available: false,
            reason: Some(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        },
        Err(error) => EngineCapability {
            engine,
            available: false,
            reason: Some(format!("failed to start Python probe: {error}")),
        },
    }
}

fn model_argument_for_probe(engine: LocalEngine) -> Result<String, String> {
    model_argument(engine, LocalModel::Small).or_else(|_| model_argument(engine, LocalModel::Base))
}

fn model_argument(engine: LocalEngine, model: LocalModel) -> Result<String, String> {
    let specific_key = format!(
        "OMI_{}_MODEL_DIR_{}",
        engine_env_prefix(engine),
        model.as_str().to_ascii_uppercase()
    );
    if let Ok(value) = env::var(&specific_key) {
        if !value.is_empty() && Path::new(&value).exists() {
            return Ok(value);
        }
    }

    let general_key = format!("OMI_{}_MODEL_DIR", engine_env_prefix(engine));
    if let Ok(value) = env::var(&general_key) {
        if !value.is_empty() && Path::new(&value).exists() {
            return Ok(value);
        }
    }

    Ok(default_remote_model(engine, model).to_string())
}

fn engine_env_prefix(engine: LocalEngine) -> &'static str {
    match engine {
        LocalEngine::MlxWhisper => "MLX_WHISPER",
        LocalEngine::FasterWhisper => "FASTER_WHISPER",
    }
}

fn default_remote_model(engine: LocalEngine, model: LocalModel) -> &'static str {
    match engine {
        LocalEngine::MlxWhisper => match model {
            LocalModel::Tiny => "mlx-community/whisper-tiny-mlx",
            LocalModel::Base => "mlx-community/whisper-base-mlx",
            LocalModel::Small => "mlx-community/whisper-small-mlx",
            LocalModel::Medium => "mlx-community/whisper-medium-mlx",
            LocalModel::LargeV3Turbo => "mlx-community/whisper-large-v3-turbo",
        },
        LocalEngine::FasterWhisper => match model {
            LocalModel::Tiny => "Systran/faster-whisper-tiny",
            LocalModel::Base => "Systran/faster-whisper-base",
            LocalModel::Small => "Systran/faster-whisper-small",
            LocalModel::Medium => "Systran/faster-whisper-medium",
            LocalModel::LargeV3Turbo => "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        },
    }
}

fn python_executable() -> String {
    env::var("OMI_LOCAL_ASR_PYTHON").unwrap_or_else(|_| "python3".to_string())
}

fn is_native_apple_silicon() -> bool {
    if env::consts::ARCH != "aarch64" {
        return false;
    }
    let translated = Command::new("sysctl")
        .args(["-in", "sysctl.proc_translated"])
        .output()
        .ok()
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|value| value.trim() == "1")
        .unwrap_or(false);
    !translated
}

const PYTHON_PROBE: &str = r#"
import os
import sys

engine = sys.argv[1]
model = sys.argv[2]

if not model:
    raise SystemExit("no local model is configured for this engine")

if engine == "mlx-whisper":
    import mlx_whisper  # noqa: F401
elif engine == "faster-whisper":
    import faster_whisper  # noqa: F401
else:
    raise SystemExit(f"unknown engine: {engine}")

if os.path.exists(model):
    print("ok")
else:
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=model,
        local_files_only=os.environ.get("OMI_LOCAL_ASR_ALLOW_MODEL_DOWNLOAD") != "1",
    )
    print("ok")
"#;

const PYTHON_TRANSCRIBE: &str = r#"
import json
import os
import sys

engine, model, audio_path, language = sys.argv[1:5]
language = None if language in ("", "auto") else language

def resolve_model(model):
    if os.path.exists(model):
        return model
    from huggingface_hub import snapshot_download
    return snapshot_download(
        repo_id=model,
        local_files_only=os.environ.get("OMI_LOCAL_ASR_ALLOW_MODEL_DOWNLOAD") != "1",
    )

def clean_segments(raw_segments):
    segments = []
    for index, segment in enumerate(raw_segments):
        if isinstance(segment, dict):
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start))
            text = str(segment.get("text", "")).strip()
            sid = segment.get("id", index)
        else:
            start = float(getattr(segment, "start", 0.0))
            end = float(getattr(segment, "end", start))
            text = str(getattr(segment, "text", "")).strip()
            sid = getattr(segment, "id", index)
        if text:
            segments.append({
                "id": f"local-{sid}",
                "speaker": 0,
                "text": text,
                "start": start,
                "end": end,
            })
    return segments

if engine == "mlx-whisper":
    import mlx_whisper
    model = resolve_model(model)
    result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=model, language=language, verbose=False)
    raw_segments = result.get("segments", [])
elif engine == "faster-whisper":
    from faster_whisper import WhisperModel
    allow_download = os.environ.get("OMI_LOCAL_ASR_ALLOW_MODEL_DOWNLOAD") == "1"
    model = resolve_model(model)
    whisper = WhisperModel(model, device="auto", compute_type="auto", local_files_only=not allow_download)
    raw_segments, _ = whisper.transcribe(audio_path, language=language, vad_filter=True)
else:
    raise SystemExit(f"unknown engine: {engine}")

print(json.dumps(clean_segments(raw_segments)))
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_fixture_request_contract() {
        let json = r#"{
          "request_id": "req-1",
          "audio_path": "/tmp/audio.pcm",
          "language": "en",
          "sample_rate": 16000,
          "channels": 1,
          "engine": "mlx-whisper",
          "model": "small",
          "fixture_segments": [
            {"id": "seg-1", "speaker": 0, "text": "hello", "start": 0.0, "end": 1.0}
          ]
        }"#;

        let request: TranscriptionRequest = serde_json::from_str(json).unwrap();

        assert_eq!(request.engine, LocalEngine::MlxWhisper);
        assert_eq!(request.model, LocalModel::Small);
        assert_eq!(request.fixture_segments.unwrap()[0].text, "hello");
    }

    #[test]
    fn writes_pcm_as_wav() {
        let source = env::temp_dir().join("omi-local-asr-test.pcm");
        fs::write(&source, [0u8, 0, 1, 0]).unwrap();

        let wav = write_wav_copy(&source, "unit-test").unwrap();
        let bytes = fs::read(&wav).unwrap();

        assert_eq!(&bytes[0..4], b"RIFF");
        assert_eq!(&bytes[8..12], b"WAVE");
        assert_eq!(&bytes[44..], &[0u8, 0, 1, 0]);

        let _ = fs::remove_file(source);
        let _ = fs::remove_file(wav);
    }

    #[test]
    fn capability_response_contract_round_trips() {
        let response = CapabilityResponse {
            engines: vec![EngineCapability {
                engine: LocalEngine::FasterWhisper,
                available: false,
                reason: Some("missing model".to_string()),
            }],
        };

        let json = serde_json::to_string(&response).unwrap();
        let decoded: CapabilityResponse = serde_json::from_str(&json).unwrap();

        assert_eq!(decoded, response);
    }
}
