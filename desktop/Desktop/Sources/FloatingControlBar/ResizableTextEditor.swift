import Cocoa
import SwiftUI

/// Auto-resizing NSTextView wrapper for the floating control bar input.
struct ResizableTextEditor: NSViewRepresentable {
    @Binding var text: String
    let minHeight: CGFloat
    let maxHeight: CGFloat
    let onHeightChange: (CGFloat) -> Void
    var onSubmit: (() -> Void)?

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let textView = scrollView.documentView as? NSTextView else {
            return scrollView
        }

        textView.font = .systemFont(ofSize: 13)
        textView.textColor = .white
        textView.backgroundColor = .clear
        textView.drawsBackground = false
        textView.isRichText = false
        textView.allowsUndo = true
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isAutomaticTextReplacementEnabled = false
        textView.delegate = context.coordinator

        textView.textContainer?.lineFragmentPadding = 8
        textView.textContainerInset = NSSize(width: 0, height: 8)
        textView.textContainer?.widthTracksTextView = true

        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.backgroundColor = .clear
        scrollView.drawsBackground = false

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }

        if textView.string != text {
            textView.string = text
            context.coordinator.updateHeight(for: textView, scrollView: scrollView)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text,
            minHeight: minHeight,
            maxHeight: maxHeight,
            onHeightChange: onHeightChange,
            onSubmit: onSubmit
        )
    }

    class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: String
        let minHeight: CGFloat
        let maxHeight: CGFloat
        let onHeightChange: (CGFloat) -> Void
        let onSubmit: (() -> Void)?
        private var lastHeight: CGFloat = 0

        init(
            text: Binding<String>, minHeight: CGFloat, maxHeight: CGFloat,
            onHeightChange: @escaping (CGFloat) -> Void,
            onSubmit: (() -> Void)?
        ) {
            self._text = text
            self.minHeight = minHeight
            self.maxHeight = maxHeight
            self.onHeightChange = onHeightChange
            self.onSubmit = onSubmit
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            self.text = textView.string

            if let scrollView = textView.enclosingScrollView {
                self.updateHeight(for: textView, scrollView: scrollView)
            }
        }

        func textView(_ textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            // Enter without shift submits
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
            guard let layoutManager = textView.layoutManager,
                  let textContainer = textView.textContainer
            else { return }

            layoutManager.ensureLayout(for: textContainer)
            let usedRect = layoutManager.usedRect(for: textContainer)
            let contentHeight = usedRect.height + textView.textContainerInset.height * 2
            let constrainedHeight = min(max(contentHeight, minHeight), maxHeight)

            if abs(constrainedHeight - lastHeight) > 1 {
                lastHeight = constrainedHeight
                onHeightChange(constrainedHeight)
            }
        }
    }
}
