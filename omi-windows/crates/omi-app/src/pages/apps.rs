use dioxus::prelude::*;

#[component]
pub fn AppsPage() -> Element {
    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Apps" }
            p { class: "page-subtitle", "Browse and install plugins and integrations." }

            div { class: "card-grid",
                div { class: "card",
                    h3 { "Slack" }
                    p { class: "text-muted", "Send conversation summaries to Slack channels." }
                }
                div { class: "card",
                    h3 { "GitHub" }
                    p { class: "text-muted", "Create issues from action items." }
                }
                div { class: "card",
                    h3 { "Notion" }
                    p { class: "text-muted", "Export memories and notes to Notion." }
                }
                div { class: "card",
                    h3 { "Google Calendar" }
                    p { class: "text-muted", "Link conversations to calendar events." }
                }
            }
        }
    }
}
