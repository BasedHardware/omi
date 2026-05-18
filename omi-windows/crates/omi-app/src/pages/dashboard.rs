use dioxus::prelude::*;

#[component]
pub fn DashboardPage() -> Element {
    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Dashboard" }
            p { class: "page-subtitle", "Overview of recent activity, conversations, and stats." }

            div { class: "card-grid",
                div { class: "card",
                    h3 { "Recent Conversations" }
                    p { class: "text-muted", "No conversations yet. Start recording to see them here." }
                }
                div { class: "card",
                    h3 { "Memories" }
                    p { class: "text-muted", "Your extracted memories will appear here." }
                }
                div { class: "card",
                    h3 { "Action Items" }
                    p { class: "text-muted", "Tasks extracted from conversations." }
                }
                div { class: "card",
                    h3 { "Screen Time" }
                    p { class: "text-muted", "Screen capture stats will be shown here." }
                }
            }
        }
    }
}
