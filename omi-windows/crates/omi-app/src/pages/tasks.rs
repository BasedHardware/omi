use dioxus::prelude::*;

#[component]
pub fn TasksPage() -> Element {
    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Tasks" }
            p { class: "page-subtitle", "Action items extracted from your conversations." }

            div { class: "empty-state",
                p { "No tasks yet." }
                p { class: "text-muted", "Action items are automatically detected from conversations." }
            }
        }
    }
}
