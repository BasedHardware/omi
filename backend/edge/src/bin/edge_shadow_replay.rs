//! Offline D2 replay: feed recorded mirror streams through the same
//! [`ShadowCore`] the `/v1/shadow` endpoint uses and print one JSON summary
//! line per stream.
//!
//! Usage: `edge-shadow-replay <model.onnx> <stream>...`
//!
//! A stream file is a sequence of records, each a big-endian u32 length and
//! that many bytes. The first record is the handshake query
//! (`v=1&codec=..&sample_rate=..&session=..`); every later record is one
//! binary mirror message, exactly as listen would send it.
use std::process::ExitCode;
use std::sync::Arc;

use omi_edge::metrics::{Metrics, ShadowOutcome};
use omi_edge::shadow::{ShadowCore, ShadowMeta, Summary};

fn records(bytes: &[u8]) -> Result<Vec<&[u8]>, String> {
    let mut out = Vec::new();
    let mut rest = bytes;
    while !rest.is_empty() {
        if rest.len() < 4 {
            return Err("truncated record length".into());
        }
        let n = u32::from_be_bytes(rest[..4].try_into().unwrap()) as usize;
        if rest.len() < 4 + n {
            return Err("truncated record".into());
        }
        out.push(&rest[4..4 + n]);
        rest = &rest[4 + n..];
    }
    Ok(out)
}

fn json(name: &str, meta: &ShadowMeta, outcome: ShadowOutcome, s: &Summary) -> String {
    let c = &s.compare;
    let mut offsets: Vec<u64> = s.open_offsets_samples.clone();
    offsets.sort_unstable();
    let offsets_ms: Vec<String> = offsets
        .iter()
        .map(|o| format!("{:.3}", *o as f64 * 1000.0 / meta.sample_rate as f64))
        .collect();
    let opt = |v: Option<f64>| v.map(|x| format!("{x:.6}")).unwrap_or_else(|| "null".into());
    format!(
        concat!(
            "{{\"stream\":\"{}\",\"codec\":\"{}\",\"sample_rate\":{},\"outcome\":\"{}\",",
            "\"variant\":\"{}\",\"hangover_ms\":{},\"aligned\":{},\"frames\":{},\"decode_errors\":{},",
            "\"length_mismatches\":{},\"audio_seconds\":{:.3},\"edge_windows\":{},",
            "\"agree_speech\":{},\"agree_silence\":{},\"edge_speech_only\":{},\"listen_speech_only\":{},",
            "\"not_comparable\":{},\"unmatched\":{},\"agreement\":{},\"max_prob_diff\":{:e},",
            "\"opens_matched\":{},\"opens_listen_only\":{},\"opens_edge_only\":{},\"open_offsets_ms\":[{}],",
            "\"decode_ms_per_audio_s\":{:.4},\"vad_ms_per_audio_s\":{:.4}}}"
        ),
        name.replace('"', "'"),
        meta.codec.as_str(),
        meta.sample_rate,
        outcome.as_str(),
        s.variant.map(|v| v.as_str()).unwrap_or("none"),
        opt(s.hangover_ms),
        s.aligned,
        s.frames,
        s.decode_errors,
        s.length_mismatches,
        s.audio_samples as f64 / meta.sample_rate as f64,
        s.edge_windows,
        c[0],
        c[1],
        c[2],
        c[3],
        c[4],
        c[5],
        opt(s.agreement()),
        s.max_prob_diff,
        s.opens[0],
        s.opens[1],
        s.opens[2],
        offsets_ms.join(","),
        per_audio_ms(s.decode_seconds, s, meta),
        per_audio_ms(s.vad_seconds, s, meta),
    )
}

fn per_audio_ms(seconds: f64, s: &Summary, meta: &ShadowMeta) -> f64 {
    let audio = s.audio_samples as f64 / meta.sample_rate as f64;
    if audio > 0.0 {
        seconds * 1000.0 / audio
    } else {
        0.0
    }
}

fn replay(path: &str, metrics: &Arc<Metrics>) -> Result<String, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("{path}: {e}"))?;
    let recs = records(&bytes).map_err(|e| format!("{path}: {e}"))?;
    let (head, msgs) = recs.split_first().ok_or_else(|| format!("{path}: empty stream"))?;
    let query = std::str::from_utf8(head).map_err(|_| format!("{path}: query is not utf-8"))?;
    let meta = ShadowMeta::from_query(query).map_err(|e| format!("{path}: {e}"))?;
    let mut core = ShadowCore::new(meta.clone(), metrics.clone())?;
    let mut outcome = ShadowOutcome::Completed;
    for m in msgs {
        if let Err(o) = core.on_message(m) {
            outcome = o;
            break;
        }
    }
    let summary = core.finish(outcome);
    let name = std::path::Path::new(path)
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();
    Ok(json(&name, &meta, outcome, &summary))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let Some((model, streams)) = args.split_first() else {
        eprintln!("usage: edge-shadow-replay <model.onnx> <stream>...");
        return ExitCode::from(2);
    };
    if let Err(e) = omi_edge::silero::init(model) {
        eprintln!("model: {e}");
        return ExitCode::from(2);
    }
    let metrics = Arc::new(Metrics::new(""));
    let mut failed = false;
    for path in streams {
        match replay(path, &metrics) {
            Ok(line) => println!("{line}"),
            Err(e) => {
                eprintln!("{e}");
                failed = true;
            }
        }
    }
    if failed {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}
