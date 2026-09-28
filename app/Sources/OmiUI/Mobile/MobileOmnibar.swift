import SwiftUI

// Mobile omnibar, ported from `react-native/src/mobile/MobileOmnibar.tsx`:
// Ask/Search mode toggles inline to the left of one shared draft, a
// translucent rounded field, and a single submit/stop affordance. Mobile has
// no Live voice button and no phone shortcut — Ask and Search only.

public enum MobileOmnibarMode: String {
    case ask = "Ask"
    case search = "Search"
}

public struct MobileOmnibar: View {
    @Binding public var mode: MobileOmnibarMode
    @Binding public var value: String
    public let busy: Bool
    public let canStop: Bool
    public let onSubmit: () -> Void
    public let onStop: () -> Void

    public init(
        mode: Binding<MobileOmnibarMode>, value: Binding<String>, busy: Bool,
        canStop: Bool, onSubmit: @escaping () -> Void, onStop: @escaping () -> Void
    ) {
        self._mode = mode
        self._value = value
        self.busy = busy
        self.canStop = canStop
        self.onSubmit = onSubmit
        self.onStop = onStop
    }

    private var stopping: Bool { mode == .ask && canStop }

    private var disabled: Bool {
        if stopping { return false }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return true }
        return mode == .ask && busy
    }

    public var body: some View {
        HStack(spacing: 0) {
            modeToggle(.ask)
            modeToggle(.search)
            TextField(
                mode == .ask ? "Ask anything…" : "Search Omi…",
                text: $value,
                onCommit: submit
            )
            .font(TypeStyle(size: 16, lineHeight: 22, weight: .regular).font)
            .foregroundColor(MobilePalette.text)
            .padding(.horizontal, 8)
            .frame(minHeight: 44)
            .accessibilityLabel(mode == .ask ? "Ask Omi" : "Search loaded data")
            .submitLabel(mode == .ask ? .send : .search)
            if mode == .search, !value.isEmpty {
                clearButton
            }
            submitButton
        }
        .padding(6)
        .background(MobilePalette.omnibarField)
        .overlay(
            RoundedRectangle(cornerRadius: 22)
                .strokeBorder(MobilePalette.border, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .accessibilityLabel("Ask and search dock")
    }

    private func modeToggle(_ item: MobileOmnibarMode) -> some View {
        let selected = mode == item
        return Button(action: { mode = item }) {
            ZStack {
                RoundedRectangle(cornerRadius: MobileRadius.chip)
                    .fill(selected ? MobilePalette.surfaceRaised : Color.clear)
                KitIcon(
                    item == .ask ? .chatBubble : .search, size: 19,
                    color: selected ? MobilePalette.text : MobilePalette.textMuted
                )
            }
            .frame(width: 44, height: 44)
        }
        .buttonStyle(KitPressableStyle())
        .animation(KitMotion.slide, value: mode)
        .accessibilityLabel("\(item.rawValue) mode")
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }

    private var clearButton: some View {
        Button(action: { value = "" }) {
            KitIcon(.close, size: 18, color: MobilePalette.textMuted)
                .frame(width: 44, height: 44)
        }
        .buttonStyle(KitPressableStyle())
        .accessibilityLabel("Clear search")
    }

    private var submitButton: some View {
        Button(action: submit) {
            submitGlyph
                .frame(width: 44, height: 44)
                .background(
                    RoundedRectangle(cornerRadius: MobileRadius.chip)
                        .fill(MobilePalette.text)
                )
        }
        .buttonStyle(KitPressableStyle())
        .opacity(disabled ? 0.35 : 1)
        .disabled(disabled)
        .accessibilityLabel(submitLabel)
    }

    @ViewBuilder
    private var submitGlyph: some View {
        if stopping {
            KitIcon(.stop, size: 14, color: MobilePalette.background, filled: true)
        } else if mode == .ask {
            KitIcon(.arrowUp, size: 20, color: MobilePalette.background)
        } else {
            KitIcon(.search, size: 18, color: MobilePalette.background)
        }
    }

    private var submitLabel: String {
        if stopping { return "Stop response" }
        return mode == .ask ? "Send to Omi" : "Search loaded data"
    }

    private func submit() {
        if disabled { return }
        if stopping {
            onStop()
        } else {
            onSubmit()
        }
    }
}
