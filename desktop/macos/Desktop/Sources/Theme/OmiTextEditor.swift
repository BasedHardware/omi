import Cocoa
import SwiftUI

/// NSScrollView subclass that auto-focuses its NSTextView when added to a window.
private class AutoFocusScrollView: NSScrollView {
    var shouldFocusOnAppear = false

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard shouldFocusOnAppear, let window = self.window,
              let textView = self.documentView as? NSTextView else { return }
        shouldFocusOnAppear = false
        DispatchQueue.main.async {
            window.makeKeyAndOrderFront(nil)
            window.makeFirstResponder(textView)
        }
    }
}

/// NSTextView subclass that reports IME marked-text composition state.
private class OmiNSTextView: NSTextView {
    var onMarkedTextStatusChange: ((Bool) -> Void)?

    override func setMarkedText(_ string: Any, selectedRange: NSRange, replacementRange: NSRange) {
        super.setMarkedText(string, selectedRange: selectedRange, replacementRange: replacementRange)
        publishMarkedTextStatus()
    }

    override func unmarkText() {
        super.unmarkText()
        publishMarkedTextStatus()
    }

    override func insertText(_ string: Any, replacementRange: NSRange) {
        super.insertText(string, replacementRange: replacementRange)
        publishMarkedTextStatus()
    }

    private func publishMarkedTextStatus() {
        onMarkedTextStatusChange?(hasMarkedText())
    }
}

/// Unified NSTextView wrapper used by both the main chat input and the floating control bar.
struct OmiTextEditor: NSViewRepresentable {
    @Binding var text: String

    // Appearance
    var fontSize: CGFloat = 13
    var textColor: NSColor = .white
    var lineFragmentPadding: CGFloat = 0
    var textContainerInset: NSSize = NSSize(width: 0, height: 8)

    // Behavior
    var onSubmit: (() -> Void)? = nil
    var focusOnAppear: Bool = true
    var onMarkedTextChange: ((Bool) -> Void)? = nil

    // Optional height tracking (for floating bar's window resize flow)
    var minHeight: CGFloat? = nil
    var maxHeight: CGFloat? = nil
    var onHeightChange: ((CGFloat) -> Void)? = nil

    func makeNSView(context: Context) -> NSScrollView {
        let textView = OmiNSTextView()
        textView.font = .systemFont(ofSize: fontSize)
        textView.textColor = textColor
        textView.backgroundColor = .clear
        textView.drawsBackground = false
        textView.isRichText = false
        textView.allowsUndo = true
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isAutomaticTextReplacementEnabled = false
        textView.delegate = context.coordinator
        textView.onMarkedTextStatusChange = { [weak coordinator = context.coordinator] hasMarkedText in
            coordinator?.updateMarkedTextState(hasMarkedText)
        }

        textView.textContainer?.lineFragmentPadding = lineFragmentPadding
        textView.textContainerInset = textContainerInset
        textView.textContainer?.widthTracksTextView = true
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.maxSize = NSSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude
        )

        let scrollView: NSScrollView
        if focusOnAppear {
            let autoFocus = AutoFocusScrollView()
            autoFocus.shouldFocusOnAppear = true
            scrollView = autoFocus
        } else {
            scrollView = NSScrollView()
        }

        scrollView.documentView = textView
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.backgroundColor = .clear
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }

        // Keep the coordinator's binding fresh so textDidChange writes to the
        // correct task's draftText when SwiftUI reuses this NSView across tasks.
        context.coordinator.updateTextBinding($text)

        if textView.string != text, !textView.hasMarkedText() {
            context.coordinator.isUpdating = true
            textView.string = text
            context.coordinator.isUpdating = false

            // Force layout so NSScrollView knows the new content size
            // (needed for programmatic text changes to show scrollbar)
            if let layoutManager = textView.layoutManager,
               let textContainer = textView.textContainer {
                layoutManager.ensureLayout(for: textContainer)
            }

            // When text is cleared (e.g. after submit), scroll back to the top
            // so the empty input isn't left in a scrolled-down position.
            if text.isEmpty {
                textView.scrollRangeToVisible(NSRange(location: 0, length: 0))
            }

            if onHeightChange != nil {
                context.coordinator.updateHeight(for: textView, scrollView: scrollView)
            }

            // Re-focus the text view when content changes programmatically
            // (e.g. switching between task chats reuses this NSView).
            // Guard: skip if the text view already has focus to avoid a
            // focus-thrash loop with SwiftUI's SelectionOverlay.
            if focusOnAppear, let window = scrollView.window,
               window.firstResponder !== textView {
                DispatchQueue.main.async {
                    guard window.firstResponder !== textView else { return }
                    window.makeFirstResponder(textView)
                }
            }
        }

        // Keep closures fresh so they capture the latest SwiftUI state
        context.coordinator.onSubmit = onSubmit
        context.coordinator.onMarkedTextChange = onMarkedTextChange

        let newFont = NSFont.systemFont(ofSize: fontSize)
        if textView.font != newFont {
            textView.font = newFont
        }

        context.coordinator.updateMarkedTextState(textView.hasMarkedText())
    }

    /// Return a concrete size to SwiftUI's layout engine so it doesn't have to
    /// recurse through the parent hierarchy to infer the editor's height.
    /// Without this, NSViewRepresentable reports no intrinsic size and SwiftUI
    /// keeps propagating unconstrained proposals upward, contributing to the
    /// recursive StackLayout sizing loop seen in the task chat panel.
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSScrollView, context: Context) -> CGSize? {
        guard let minH = minHeight, let maxH = maxHeight else {
            return nil  // no height tracking — let SwiftUI use default NSView sizing
        }
        guard let textView = nsView.documentView as? NSTextView,
              let layoutManager = textView.layoutManager,
              let textContainer = textView.textContainer else {
            return CGSize(width: proposal.width ?? nsView.bounds.width, height: minH)
        }
        layoutManager.ensureLayout(for: textContainer)
        let usedRect = layoutManager.usedRect(for: textContainer)
        let contentHeight = usedRect.height + textView.textContainerInset.height * 2
        let constrainedHeight = min(max(contentHeight, minH), maxH)
        return CGSize(width: proposal.width ?? nsView.bounds.width, height: constrainedHeight)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text,
            onSubmit: onSubmit,
            onMarkedTextChange: onMarkedTextChange,
            minHeight: minHeight,
            maxHeight: maxHeight,
            onHeightChange: onHeightChange
        )
    }

    class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: String
        var onSubmit: (() -> Void)?
        var onMarkedTextChange: ((Bool) -> Void)?
        var isUpdating = false

        func updateTextBinding(_ binding: Binding<String>) {
            _text = binding
        }

        // Height tracking (only used when onHeightChange is provided)
        private let minHeight: CGFloat?
        private let maxHeight: CGFloat?
        private let onHeightChange: ((CGFloat) -> Void)?
        private var lastHeight: CGFloat = 0
        private var lastMarkedTextState = false

        init(
            text: Binding<String>,
            onSubmit: (() -> Void)?,
            onMarkedTextChange: ((Bool) -> Void)?,
            minHeight: CGFloat?,
            maxHeight: CGFloat?,
            onHeightChange: ((CGFloat) -> Void)?
        ) {
            self._text = text
            self.onSubmit = onSubmit
            self.onMarkedTextChange = onMarkedTextChange
            self.minHeight = minHeight
            self.maxHeight = maxHeight
            self.onHeightChange = onHeightChange
        }

        func textDidChange(_ notification: Notification) {
            guard !isUpdating, let textView = notification.object as? NSTextView else { return }
            self.text = textView.string

            if onHeightChange != nil, let scrollView = textView.enclosingScrollView {
                updateHeight(for: textView, scrollView: scrollView)
            }

            updateMarkedTextState(textView.hasMarkedText())
        }

        func textView(_ textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            if textView.hasMarkedText() {
                return false
            }

            if commandSelector == #selector(NSResponder.insertNewline(_:)) {
                let flags = NSApp.currentEvent?.modifierFlags ?? []
                if !flags.contains(.shift) {
                    onSubmit?()
                    return true
                }
            }
            return false
        }

        func updateHeight(for textView: NSTextView, scrollView: NSScrollView) {
            guard let onHeightChange = onHeightChange,
                  let minH = minHeight, let maxH = maxHeight,
                  let layoutManager = textView.layoutManager,
                  let textContainer = textView.textContainer
            else { return }

            layoutManager.ensureLayout(for: textContainer)
            let usedRect = layoutManager.usedRect(for: textContainer)
            let contentHeight = usedRect.height + textView.textContainerInset.height * 2
            let constrainedHeight = min(max(contentHeight, minH), maxH)

            if abs(constrainedHeight - lastHeight) > 1 {
                lastHeight = constrainedHeight
                onHeightChange(constrainedHeight)
            }
        }

        func updateMarkedTextState(_ hasMarkedText: Bool) {
            guard hasMarkedText != lastMarkedTextState else { return }
            lastMarkedTextState = hasMarkedText
            DispatchQueue.main.async { [weak self] in
                guard self?.lastMarkedTextState == hasMarkedText else { return }
                self?.onMarkedTextChange?(hasMarkedText)
            }
        }
    }
}
