use dioxus::prelude::*;

#[component]
pub fn MemoriesPage() -> Element {
    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Memories" }
            p { class: "page-subtitle", "Facts and knowledge extracted from your conversations." }

            div { class: "search-bar",
                input {
                    class: "search-input",
                    r#type: "text",
                    placeholder: "Search memories...",
                }
            }

            div { class: "empty-state",
                p { "No memories yet." }
                p { class: "text-muted", "Memories are automatically extracted from your conversations." }
            }
        }
    }
}
