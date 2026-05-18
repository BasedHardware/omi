use dioxus::prelude::*;

#[component]
pub fn ConversationsPage() -> Element {
    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Conversations" }
            p { class: "page-subtitle", "Browse and search your captured conversations." }

            div { class: "empty-state",
                p { "No conversations recorded yet." }
                p { class: "text-muted", "Conversations will appear here once audio capture is running." }
            }
        }
    }
}
