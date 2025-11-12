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
            contentRect: contentRect, styleMask: [.borderless, .utilityWindow, .resizable], backing: backingStoreType,
            defer: flag)

        self.isOpaque = false
        self.backgroundColor = .clear
        self.level = .floating
        self.hasShadow = false
        self.isMovableByWindowBackground = true
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        
        // Set min and max sizes for resizing (only height, width is fixed)
        self.minSize = NSSize(width: contentRect.width, height: 150)
        self.maxSize = NSSize(width: contentRect.width, height: 800)
    }

    // Allow the window to become the key window to receive keyboard events.
    override var canBecomeKey: Bool {
        return true
    }

    // Allow the window to become the main window.
    override var canBecomeMain: Bool {
        return true
    }
    
    // Override to maintain fixed width while allowing height changes
    override func setFrame(_ frameRect: NSRect, display flag: Bool) {
        var adjustedFrame = frameRect
        // Keep width fixed to minSize width
        adjustedFrame.size.width = self.minSize.width
        super.setFrame(adjustedFrame, display: flag)
    }
}
