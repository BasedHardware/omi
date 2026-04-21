import { invoke } from "@tauri-apps/api/core";
import type { ChatStepHandler } from "../types";

const LANGUAGES: Record<string, string> = {
  en: "English",
  "pt-BR": "Português (Brasil)",
  es: "Español",
  fr: "Français",
  de: "Deutsch",
};

export const languageHandler: ChatStepHandler = {
  stepId: "language",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: (signals) =>
    `Ask ${signals.preferredName || "them"} to pick the language they'd like to use Nooto in. One short sentence, no emoji.`,
  fallbackOpener: (signals) =>
    `Nice to meet you${signals.preferredName ? ", " + signals.preferredName : ""}. Which language should I use?`,
  widget: () => ({
    type: "chips",
    allowFreeText: false,
    options: [
      { id: "en", label: "English" },
      { id: "pt-BR", label: "Português (Brasil)" },
      { id: "es", label: "Español" },
      { id: "fr", label: "Français" },
      { id: "de", label: "Deutsch" },
    ],
  }),
  summarize: (r) => {
    if ("chip" in r) return LANGUAGES[r.chip] ?? r.chip;
    return null;
  },
  onCapture: async (r, ctx) => {
    const lang = "chip" in r ? r.chip : null;
    if (!lang) return;
    ctx.onboarding.setLanguage(lang);
    ctx.companion.updateSignals({ language: LANGUAGES[lang] ?? lang });
    try {
      await invoke("set_user_language", { language: lang });
    } catch {
      /* best-effort */
    }
    ctx.onboarding.advance();
  },
};
