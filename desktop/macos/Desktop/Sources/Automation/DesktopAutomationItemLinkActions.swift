//
//  DesktopAutomationItemLinkActions.swift — drive app-scheme item links without the cursor.
//
//  `item_link_open` hands a URL to the same `ItemLinkPresenter.receive` the Apple-event URL handler
//  calls, then waits for the signed-in shell to resolve it. It is a second caller of production
//  code, not a second implementation. Registered from `DesktopAutomationActionRegistry.registerBuiltins()`.
//

import Foundation

extension DesktopAutomationActionRegistry {

  func registerItemLinkActions() {
    register(
      name: "item_link_open",
      effects: [.localState, .networkOrModel],
      summary: "Open an app-scheme item link (items?…, conversation/<id>, task/<id>, memory/<id>) and wait for it",
      params: ["url", "timeoutMs"],
      examples: [
        "./scripts/omi-ctl action item_link_open url='omi-computer-dev://items?conversation=a&task=b'"
      ]
    ) { params in
      let raw = (params["url"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard let url = URL(string: raw) else { return ["error": "url is not a URL"] }
      let presenter = ItemLinkPresenter.shared
      let settledBefore = presenter.settledCount
      guard presenter.receive(url, revealsWindow: false) else {
        return ["handled": "false"]
      }
      let timeoutMs = max(500, Int(params["timeoutMs"] ?? "") ?? 10_000)
      let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1_000)
      // omi-test-quality: wall-clock-wait -- the shell resolves the link on its own task; this
      // bounded poll observes the presenter's settle counter, the same pattern as open_conversation.
      while presenter.settledCount == settledBefore, Date() < deadline {
        try await Task.sleep(nanoseconds: 50_000_000)
      }
      var result = Self.itemLinkSnapshot(presenter)
      result["handled"] = "true"
      result["settled"] = presenter.settledCount != settledBefore ? "true" : "false"
      return result
    }

    register(
      name: "item_link_snapshot",
      effects: [],
      summary: "Report the item-link sheet and the last record an item link opened",
      examples: ["./scripts/omi-ctl action item_link_snapshot --read-only"]
    ) { _ in
      Self.itemLinkSnapshot(ItemLinkPresenter.shared)
    }

    register(
      name: "item_link_dismiss",
      effects: [.localState],
      summary: "Close the item-link sheet (same handler as its close button)",
      examples: ["./scripts/omi-ctl action item_link_dismiss"]
    ) { _ in
      ItemLinkPresenter.shared.dismiss()
      return Self.itemLinkSnapshot(ItemLinkPresenter.shared)
    }
  }

  private static func itemLinkSnapshot(_ presenter: ItemLinkPresenter) -> [String: String] {
    let rows = presenter.sheet?.rows
    return [
      "sheet_open": presenter.sheet == nil ? "false" : "true",
      "sheet_loading": presenter.sheet != nil && rows == nil ? "true" : "false",
      "row_count": String(rows?.count ?? 0),
      "available_count": String(rows?.filter(\.isAvailable).count ?? 0),
      "unavailable_count": String(rows?.filter { !$0.isAvailable }.count ?? 0),
      "row_kinds": (rows ?? []).map(\.reference.kind.rawValue).joined(separator: ","),
      "last_opened_kind": presenter.lastOpened?.kind.rawValue ?? "",
    ]
  }
}
