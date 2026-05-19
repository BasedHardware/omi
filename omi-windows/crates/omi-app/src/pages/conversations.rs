use dioxus::prelude::*;

use crate::recording::{LiveTranscript, RecordingStatus};

#[component]
pub fn ConversationsPage() -> Element {
    let recording_status: Signal<RecordingStatus> = use_context();
    let live_transcript: Signal<LiveTranscript> = use_context();

    let is_recording = matches!(*recording_status.read(), RecordingStatus::Recording { .. });
    let segments = live_transcript.read().segments.clone();
    let has_segments = !segments.is_empty();

    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Conversations" }
            p { class: "page-subtitle",
                if is_recording {
                    "Live conversation in progress..."
                } else {
                    "Browse and search your captured conversations."
                }
            }

            if has_segments {
                // Current / most recent conversation
                div { class: "conversation-card",
                    div { class: "conversation-header",
                        h3 {
                            if is_recording { "Current Session" } else { "Last Session" }
                        }
                        span { class: "conversation-meta",
                            "{segments.iter().filter(|s| s.is_final).count()} segments"
                        }
                    }
                    div { class: "conversation-transcript",
                        for seg in segments.iter().filter(|s| s.is_final) {
                            div { class: "transcript-segment final",
                                span { class: "speaker-badge", "S{seg.speaker}" }
                                span { class: "segment-text", "{seg.text}" }
                            }
                        }
                        // Show current interim at the bottom
                        if let Some(interim) = segments.iter().rfind(|s| !s.is_final) {
                            div { class: "transcript-segment interim",
                                span { class: "speaker-badge", "S{interim.speaker}" }
                                span { class: "segment-text", "{interim.text}" }
                            }
                        }
                    }
                }
            } else {
                div { class: "empty-state",
                    p { "No conversations recorded yet." }
                    p { class: "text-muted", "Go to Dashboard and start recording to capture conversations." }
                }
            }
        }
    }
}
