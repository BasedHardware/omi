use dioxus::prelude::*;

#[component]
pub fn ChatPage() -> Element {
    let mut input = use_signal(String::new);

    rsx! {
        div { class: "page page-chat",
            h1 { class: "page-title", "Chat" }
            p { class: "page-subtitle", "Talk to your AI — it remembers everything you've seen and heard." }

            div { class: "chat-messages",
                div { class: "chat-empty",
                    p { "Start a conversation. Your memories and context will be used automatically." }
                }
            }

            div { class: "chat-input-bar",
                input {
                    class: "chat-input",
                    r#type: "text",
                    placeholder: "Ask anything...",
                    value: "{input}",
                    oninput: move |e| input.set(e.value()),
                }
                button { class: "btn btn-primary", "Send" }
            }
        }
    }
}
