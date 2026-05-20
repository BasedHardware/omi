use serde::{Deserialize, Serialize};
use std::io::{self, Read};
use std::process;

#[derive(Debug, Deserialize, Serialize, PartialEq)]
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

#[derive(Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "kebab-case")]
enum LocalEngine {
    MlxWhisper,
    FasterWhisper,
}

#[derive(Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum LocalModel {
    Tiny,
    Base,
    Small,
    Medium,
    LargeV3Turbo,
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

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let request = read_request()?;
    let fixture_segments = request.fixture_segments.clone().unwrap_or_else(|| {
        vec![TranscriptSegment {
            id: Some(format!("{}-fixture-0", request.request_id)),
            speaker: Some(0),
            text: "fixture local transcription".to_string(),
            start: 0.0,
            end: 1.0,
        }]
    });

    let response = TranscriptionResponse {
        request_id: request.request_id,
        engine: request.engine,
        model: request.model,
        language: request.language,
        segments: fixture_segments,
        fixture: true,
    };

    let json = serde_json::to_string(&response).map_err(|error| error.to_string())?;
    println!("{json}");
    Ok(())
}

fn read_request() -> Result<TranscriptionRequest, String> {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|error| format!("failed to read stdin: {error}"))?;
    serde_json::from_str(&input).map_err(|error| format!("invalid request json: {error}"))
}

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
}
