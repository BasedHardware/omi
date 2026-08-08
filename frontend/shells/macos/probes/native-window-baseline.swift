// Memory-footprint control: the same window, rendered natively (AppKit table of
// 60 rows + a text field), so the webview cost can be measured as a delta.
// Build: swiftc -O -framework AppKit -o <out>/NativeBaseline probes/native-window-baseline.swift
import AppKit

@MainActor
final class Delegate: NSObject, NSApplicationDelegate, NSTableViewDataSource {
  var window: NSWindow!
  func applicationDidFinishLaunching(_ n: Notification) {
    let table = NSTableView()
    table.addTableColumn(NSTableColumn(identifier: .init("c")))
    table.dataSource = self
    table.headerView = nil
    let scroll = NSScrollView()
    scroll.documentView = table
    scroll.hasVerticalScroller = true
    let field = NSTextField(string: "capture.sampleRateHz")
    let stack = NSStackView(views: [field, NSButton(title: "startCapture", target: nil, action: nil), scroll])
    stack.orientation = .vertical
    stack.edgeInsets = NSEdgeInsets(top: 16, left: 16, bottom: 16, right: 16)
    window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 960, height: 680),
      styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
    window.title = "Native Baseline"
    window.contentView = stack
    window.center()
    window.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)
  }
  func numberOfRows(in tableView: NSTableView) -> Int { 60 }
  func tableView(_ t: NSTableView, objectValueFor c: NSTableColumn?, row: Int) -> Any? {
    "momentum scroll row \(row + 1)"
  }
}

MainActor.assumeIsolated {
  let app = NSApplication.shared
  let d = Delegate()
  app.delegate = d
  app.setActivationPolicy(.regular)
  objc_setAssociatedObject(app, "omi.delegate", d, .OBJC_ASSOCIATION_RETAIN)
  app.run()
}
