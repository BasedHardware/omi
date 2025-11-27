//
//  AskAIInputWindow.swift
//  Runner
//
//  Created by Omi on 2025-09-26.
//

import Cocoa
import SwiftUI

class AIConversationWindow: NSWindow {
    override init(
        contentRect: NSRect, styleMask style: NSWindow.StyleMask = [],
        backing backingStoreType: NSWindow.BackingStoreType = .buffered, defer flag: Bool = false
    ) {
        super.init(
            contentRect: contentRect, styleMask: [.borderless, .utilityWindow], backing: backingStoreType,
            defer: flag)

        self.isOpaque = false
        self.backgroundColor = .clear
        self.level = .floating
        self.hasShadow = false
        self.isMovableByWindowBackground = true
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
    }

    // Allow the window to become the key window to receive keyboard events.
    override var canBecomeKey: Bool {
        return true
    }

    // Allow the window to become the main window.
    override var canBecomeMain: Bool {
        return true
    }
}
