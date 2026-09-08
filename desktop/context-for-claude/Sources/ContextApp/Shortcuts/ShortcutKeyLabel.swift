import Carbon.HIToolbox
import Foundation

/// What a virtual key code prints on *this* Mac's keyboard.
///
/// A key code is not a letter. `40` is `K` on a US layout and `T` on Dvorak, so a table of codes
/// baked into the app would print the wrong shortcut for anyone not typing US QWERTY. The recorder
/// takes its label off the `NSEvent` itself, which is always right — but the Settings recorder hands
/// the shortcut layer a bare `SettingsShortcutChord`, which carries only the code. That path needs
/// this: `UCKeyTranslate` against the *current* layout is the same answer the event would have given.
///
/// Falls back rather than fails. An input source with no Unicode layout data (several IMEs) returns
/// nothing translatable, and printing `Key 40` is ugly and true — which beats guessing a letter.
enum ShortcutKeyLabel {

    /// Keys whose printed form is blank, invisible, or unreadable in a one-line recorder. Everything
    /// else comes from the layout, because everything else prints itself legibly.
    static let namedKeys: [UInt16: String] = [
        UInt16(kVK_Space): "Space",
        UInt16(kVK_Tab): "⇥",
        UInt16(kVK_Delete): "⌫",
        UInt16(kVK_ForwardDelete): "⌦",
        UInt16(kVK_LeftArrow): "←",
        UInt16(kVK_RightArrow): "→",
        UInt16(kVK_UpArrow): "↑",
        UInt16(kVK_DownArrow): "↓",
        UInt16(kVK_Home): "↖",
        UInt16(kVK_End): "↘",
        UInt16(kVK_PageUp): "⇞",
        UInt16(kVK_PageDown): "⇟",
    ]

    /// - Parameter printing: the layout lookup, injectable because the live one depends on whichever
    ///   input source the machine running the tests happens to have selected — which is not something
    ///   a hermetic test may assert against.
    static func label(
        for keyCode: UInt16,
        printing: (UInt16) -> String? = { ShortcutKeyLabel.printedByCurrentLayout($0) }
    ) -> String {
        if let named = namedKeys[keyCode] { return named }
        let printed = printing(keyCode)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !printed.isEmpty else { return "Key \(keyCode)" }
        // Upper-cased to match what the recorder stores off an event, so a chord recorded through
        // either path compares equal to the same chord read out of another tool's config.
        return printed.uppercased()
    }

    /// The unmodified character the current layout puts on that key, or nil when it has none.
    ///
    /// `kUCKeyActionDisplay` with an empty modifier state is deliberately the *unshifted* legend —
    /// the letter printed on the keycap — because that is what a shortcut is written with: `⇧⌘K`,
    /// never `⇧⌘k` and never `⇧⌘˚`.
    static func printedByCurrentLayout(_ keyCode: UInt16) -> String? {
        guard let source = TISCopyCurrentKeyboardLayoutInputSource()?.takeRetainedValue(),
            let pointer = TISGetInputSourceProperty(source, kTISPropertyUnicodeKeyLayoutData)
        else {
            return nil
        }
        let layoutData = Unmanaged<CFData>.fromOpaque(pointer).takeUnretainedValue() as Data

        var deadKeyState: UInt32 = 0
        var length = 0
        var characters = [UniChar](repeating: 0, count: 4)
        var translated: String?
        layoutData.withUnsafeBytes { raw in
            guard let base = raw.baseAddress else { return }
            let layout = base.assumingMemoryBound(to: UCKeyboardLayout.self)
            let status = UCKeyTranslate(
                layout,
                keyCode,
                UInt16(kUCKeyActionDisplay),
                0,
                UInt32(LMGetKbdType()),
                // The *mask*, not `…Bit`: the bit is index 0, so passing it would silently mean "no
                // options" and let a dead key (⌥E on US) come back as an empty string.
                OptionBits(kUCKeyTranslateNoDeadKeysMask),
                &deadKeyState,
                characters.count,
                &length,
                &characters)
            guard status == noErr, length > 0 else { return }
            translated = String(utf16CodeUnits: characters, count: length)
        }
        return translated
    }
}
