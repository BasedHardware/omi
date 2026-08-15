//
//  HubDestinationSwitcher.swift — the switcher a hub page wears for its own views.
//
//  **A page's tabs belong to the page.** The Memory hub has three views — Conversations, Memories,
//  Brain Map — and until now the only control that changed between them lived in the window's top bar,
//  inside a hover menu. That is why the bar needed a menu at all: it was carrying one page's internal
//  tabs alongside the shell's actual destinations, and seven entries do not fit a row.
//
//  Moving the switcher onto the hub is not a reduced copy of anything (INV-NAV-1) — the three views
//  are the same `MemoryHubPage` branches they always were, reached by the same `MemoryHubDestination`.
//  What changes is only who shows the control, and the answer is the page whose views they are. The
//  Focus page already worked this way with `Insights / Focus`; this is that control, shared rather than
//  reimplemented.
//
//  Brand: `Ink` semantics only, two rungs (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// A minimal segmented toggle for folding related surfaces into one page.
///
/// Moved out of `DesktopHomeView` so the Memory hub and the Focus page wear the same control instead
/// of two that drift.
struct HubSegmentedControl: View {
  let segments: [String]
  @Binding var selection: Int

  var body: some View {
    HStack(spacing: 4) {
      ForEach(Array(segments.enumerated()), id: \.offset) { index, segment in
        Button {
          OmiMotion.withGated(.easeOut(duration: InkMotion.checkbox)) { selection = index }
        } label: {
          Text(segment)
            .inkStyle(.rowCopy, color: selection == index ? Ink.primary : Ink.secondary)
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            // A capsule, like every other selectable chip in this system.
            .background(GlassPillBackground(isSelected: selection == index, isHovering: false))
        }
        .buttonStyle(.plain)
      }
    }
    .padding(4)
    .background(
      Capsule(style: .continuous).fill(Ink.rowFill)
    )
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

/// The Memory hub's own three-way switcher.
///
/// Typed rather than an index into a string array: the hub's persisted destination is a
/// `MemoryHubDestination`, and a control that reports "segment 1" is one reordering away from sending
/// people to Brain Map when they asked for Conversations.
///
/// `onSelect` rather than a binding because the two shells apply a hub selection differently — the
/// modern shell writes the persisted destination, and the chat-first shell also has to move its own
/// typed route so it does not sit on `.memories` while showing Conversations.
struct MemoryHubSwitcher: View {
  let selection: MemoryHubDestination
  let onSelect: (MemoryHubDestination) -> Void

  var body: some View {
    HStack(spacing: 4) {
      ForEach(MemoryHubDestination.switcherOrder) { destination in
        Button {
          guard destination != selection else { return }
          onSelect(destination)
        } label: {
          Text(destination.title)
            .inkStyle(.rowCopy, color: destination == selection ? Ink.primary : Ink.secondary)
            .lineLimit(1)
            .fixedSize()
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(
              GlassPillBackground(isSelected: destination == selection, isHovering: false)
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(destination == selection ? .isSelected : [])
        .accessibilityIdentifier("memory-hub-destination-\(destination.rawValue)")
      }
    }
    .padding(4)
    .background(Capsule(style: .continuous).fill(Ink.rowFill))
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityIdentifier("memory-hub-switcher")
  }
}

/// How a hub selection is applied, per shell.
///
/// The chat-first shell keeps a typed route beside the persisted hub destination, so selecting a hub
/// view has to move both or the shell renders one view while claiming to be on another — which is the
/// state that made Brain Map unreachable from its Conversations route.
enum MemoryHubSelectionPolicy {
  /// The chat-first route that must be selected for a hub destination.
  ///
  /// `Conversations` has its own route (it carries capture-archive focus); the other two are the
  /// Memory route, which is where `MemoryHubPage` lives.
  static func chatFirstRoute(for destination: MemoryHubDestination) -> ChatFirstRoute {
    destination == .conversations ? .conversations : .memories
  }
}
