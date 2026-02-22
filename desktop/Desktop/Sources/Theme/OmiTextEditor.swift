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

    // Optional height tracking (for floating bar's window resize flow)
    var minHeight: CGFloat? = nil
    var maxHeight: CGFloat? = nil
    var onHeightChange: ((CGFloat) -> Void)? = nil

    func makeNSView(context: Context) -> NSScrollView {
        let textView = NSTextView()
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

        if textView.string != text {
            context.coordinator.isUpdating = true
            textView.string = text
            context.coordinator.isUpdating = false

            // Force layout and resize the text view so NSScrollView shows
            // the scrollbar for programmatic text changes (e.g. auto-inserted
            // task prompts). ensureLayout alone isn't enough — we must also
            // explicitly update the text view's frame height and re-tile the
            // scroll view, which normally happens via NSTextView's internal
            // editing flow during typing/pasting but is skipped for .string sets.
            if let layoutManager = textView.layoutManager,
               let textContainer = textView.textContainer {
                layoutManager.ensureLayout(for: textContainer)
                let usedRect = layoutManager.usedRect(for: textContainer)
                let contentHeight = usedRect.height + textView.textContainerInset.height * 2
                var tvFrame = textView.frame
                tvFrame.size.height = contentHeight
                textView.frame = tvFrame
            }

            // Re-tile the scroll view after SwiftUI finishes its layout pass
            // so it can compare document vs clip height and show scrollbar.
            DispatchQueue.main.async {
                scrollView.tile()
            }

            if onHeightChange != nil {
                context.coordinator.updateHeight(for: textView, scrollView: scrollView)
            }

            // Re-focus the text view when content changes programmatically
            // (e.g. switching between task chats reuses this NSView)
            if focusOnAppear, let window = scrollView.window {
                DispatchQueue.main.async {
                    window.makeFirstResponder(textView)
                }
            }
        }

        // Keep closures fresh so they capture the latest SwiftUI state
        context.coordinator.onSubmit = onSubmit

        let newFont = NSFont.systemFont(ofSize: fontSize)
        if textView.font != newFont {
            textView.font = newFont
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text,
            onSubmit: onSubmit,
            minHeight: minHeight,
            maxHeight: maxHeight,
            onHeightChange: onHeightChange
        )
    }

    class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: String
        var onSubmit: (() -> Void)?
        var isUpdating = false

        func updateTextBinding(_ binding: Binding<String>) {
            _text = binding
        }

        // Height tracking (only used when onHeightChange is provided)
        private let minHeight: CGFloat?
        private let maxHeight: CGFloat?
        private let onHeightChange: ((CGFloat) -> Void)?
        private var lastHeight: CGFloat = 0

        init(
            text: Binding<String>,
            onSubmit: (() -> Void)?,
            minHeight: CGFloat?,
            maxHeight: CGFloat?,
            onHeightChange: ((CGFloat) -> Void)?
        ) {
            self._text = text
            self.onSubmit = onSubmit
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
        }

        func textView(_ textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
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
    }
}
