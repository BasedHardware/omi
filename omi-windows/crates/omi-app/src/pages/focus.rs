use dioxus::prelude::*;

#[component]
pub fn FocusPage() -> Element {
    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Focus" }
            p { class: "page-subtitle", "Track your focus sessions and productivity." }

            div { class: "empty-state",
                p { "No focus sessions yet." }
                p { class: "text-muted", "Start a focus session to track your deep work time." }
            }
        }
    }
}
