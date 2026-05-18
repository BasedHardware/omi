use dioxus::prelude::*;

#[component]
pub fn RewindPage() -> Element {
    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Rewind" }
            p { class: "page-subtitle", "Browse your screen capture timeline." }

            div { class: "empty-state",
                p { "Screen capture not running." }
                p { class: "text-muted", "Enable screen capture in Settings to start recording your screen history." }
            }
        }
    }
}
