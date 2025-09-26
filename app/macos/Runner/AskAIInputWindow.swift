//
//  AskAIInputWindow.swift
//  Runner
//
//  Created by Omi on 2025-09-26.
//

import Cocoa
import SwiftUI

class AIConversationWindow: NSWindow {
    init(contentRect: NSRect, backing: NSWindow.BackingStoreType, defer flag: Bool) {
        super.init(contentRect: contentRect, styleMask: [.borderless], backing: backing, defer: flag)
        
        self.isOpaque = false
        self.backgroundColor = .clear
        self.level = .floating
        self.isMovableByWindowBackground = false
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.hasShadow = true
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
