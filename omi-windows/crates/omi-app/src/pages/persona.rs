use dioxus::prelude::*;

#[component]
pub fn PersonaPage() -> Element {
    rsx! {
        div { class: "page",
            h1 { class: "page-title", "Persona" }
            p { class: "page-subtitle", "Configure your AI assistant's personality and behavior." }

            div { class: "card",
                h3 { "Default Persona" }
                p { class: "text-muted", "Your AI adapts its responses based on context. Customize its tone and focus here." }
            }
        }
    }
}
