import OmiTheme
import SwiftUI

/// One proactive assistant's prompt, as the editor sees it: where it is read from, written to, and
/// reset. Closures rather than a protocol over the three settings singletons, so a test can hand the
/// editor a store it owns.
@MainActor
struct AssistantPromptStore {
  let title: String
  let subtitle: String
  /// The assistant's name, lowercased, for the reset confirmation ("the insight prompt").
  let noun: String
  let defaultPrompt: String
  let load: () -> String
  let save: (String) -> Void
  /// Clears the stored prompt so the shipped default applies again. Deliberately not
  /// `save(defaultPrompt)`: that would record the default as the user's own choice.
  let reset: () -> Void

  static var insight: AssistantPromptStore {
    AssistantPromptStore(
      title: "Insight Prompt",
      subtitle: "Customize the AI instructions for proactive insights",
      noun: "insight",
      defaultPrompt: InsightAssistantSettings.defaultAnalysisPrompt,
      load: { InsightAssistantSettings.shared.analysisPrompt },
      save: { InsightAssistantSettings.shared.analysisPrompt = $0 },
      reset: { InsightAssistantSettings.shared.resetPromptToDefault() })
  }

  static var task: AssistantPromptStore {
    AssistantPromptStore(
      title: "Task Extraction Prompt",
      subtitle: "Customize the AI instructions for task extraction",
      noun: "task extraction",
      defaultPrompt: TaskAssistantSettings.defaultAnalysisPrompt,
      load: { TaskAssistantSettings.shared.analysisPrompt },
      save: { TaskAssistantSettings.shared.analysisPrompt = $0 },
      reset: { TaskAssistantSettings.shared.resetPromptToDefault() })
  }

  static var memory: AssistantPromptStore {
    AssistantPromptStore(
      title: "Memory Extraction Prompt",
      subtitle: "Customize how the AI extracts memories from screenshots",
      noun: "memory extraction",
      defaultPrompt: MemoryAssistantSettings.defaultAnalysisPrompt,
      load: { MemoryAssistantSettings.shared.analysisPrompt },
      save: { MemoryAssistantSettings.shared.analysisPrompt = $0 },
      reset: { MemoryAssistantSettings.shared.resetPromptToDefault() })
  }
}

/// The editor's state: a draft that is only written on Save.
///
/// The Insight and Task editors used to write the prompt on every keystroke, so there was no way to
/// back out of an edit, and their "Done" button closed a window whose changes were already live. All
/// three editors now share this model: edit a draft, Save (⌘↩) commits it, Cancel (Esc) discards it,
/// and Reset to Default asks first.
@MainActor
final class AssistantPromptEditorModel: ObservableObject {
  let store: AssistantPromptStore
  @Published var draft: String
  @Published var isConfirmingReset = false

  /// The prompt as last committed, which is what "unsaved" is measured against.
  private var committed: String

  init(store: AssistantPromptStore) {
    self.store = store
    let current = store.load()
    committed = current
    draft = current
  }

  var hasChanges: Bool { draft != committed }

  /// Commits the draft. Returns whether anything was written.
  @discardableResult
  func save() -> Bool {
    guard hasChanges else { return false }
    store.save(draft)
    committed = draft
    return true
  }

  /// Restores the shipped default, immediately and in the store; only called after confirmation.
  func resetToDefault() {
    store.reset()
    committed = store.load()
    draft = committed
  }

  var resetMessage: String {
    "This replaces the \(store.noun) prompt with its default, including any unsaved edits. "
      + "This cannot be undone."
  }
}

/// The shared prompt editor body hosted by each assistant's editor window.
struct AssistantPromptEditorView: View {
  @StateObject private var model: AssistantPromptEditorModel
  var onClose: (() -> Void)?

  init(store: AssistantPromptStore, onClose: (() -> Void)? = nil) {
    _model = StateObject(wrappedValue: AssistantPromptEditorModel(store: store))
    self.onClose = onClose
  }

  var body: some View {
    VStack(spacing: OmiSpacing.lg) {
      header

      TextEditor(text: $model.draft)
        .scaledFont(size: OmiType.body, design: .monospaced)
        .foregroundColor(Ink.primary)
        .scrollContentBackground(.hidden)
        .padding(OmiSpacing.sm)
        .glassField()

      footer
    }
    .padding(OmiSpacing.xl)
    .frame(minWidth: 500, minHeight: 400)
    .shellConfirmation(
      isPresented: $model.isConfirmingReset,
      title: "Reset Prompt?",
      message: model.resetMessage,
      confirmTitle: "Reset"
    ) {
      model.resetToDefault()
    }
    // A titled window of its own: the dim fills this window exactly, not the main shell's lane.
    .shellModalScrimBounds(.ownSurface)
    .inkGlassPanel(cornerRadius: 0, shadow: nil)  // omi-ux-allow: literal-corner-radius -- a titled window fills its frame edge to edge; the window owns the corner
  }

  private var header: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(model.store.title)
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Text(model.store.subtitle)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      }

      Spacer()

      if model.hasChanges {
        Text("Unsaved changes")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.primary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .glassChip(isActive: true)
      }
    }
  }

  private var footer: some View {
    // While the reset confirmation is up it owns Esc and ⌘↩; the editor's own shortcuts step aside
    // so one key press cannot both answer the dialog and close the window.
    let shortcutsLive = !model.isConfirmingReset
    return HStack(spacing: OmiSpacing.sm) {
      Button("Reset to Default") {
        model.isConfirmingReset = true
      }
      .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      .disabled(model.draft == model.store.defaultPrompt && !model.hasChanges)

      Text("\(model.draft.count) characters")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      Spacer()

      Button("Cancel") {
        onClose?()
      }
      .buttonStyle(OmiButtonStyle(.secondary))
      .keyboardShortcut(shortcutsLive ? KeyboardShortcut(.escape, modifiers: []) : nil)

      Button("Save") {
        model.save()
        onClose?()
      }
      .buttonStyle(OmiButtonStyle(.primary))
      .keyboardShortcut(shortcutsLive ? KeyboardShortcut(.return, modifiers: .command) : nil)
      .disabled(!model.hasChanges)
    }
  }
}
