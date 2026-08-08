//
//  DismissableSheet.swift — click-outside-to-dismiss sheets for the shell.
//
//  A general presentation primitive that predates and outlives any one page; it lived at the bottom
//  of `AppsPage` only because that is where it was first needed. The dim it draws is a
//  `ShellModalScrim`, so it bounds itself to whichever surface it is mounted in without any call
//  site saying so.
//

import OmiTheme
import SwiftUI

/// A sheet that can be dismissed by clicking outside the content area.
/// This provides macOS-friendly modal behavior where clicking the dimmed background dismisses the sheet.
struct DismissableSheetModifier<SheetContent: View>: ViewModifier {
  @Binding var isPresented: Bool
  let sheetContent: () -> SheetContent

  func body(content: Content) -> some View {
    content
      // The overlay is modal: while it is up, the content underneath must
      // not be reachable by VoiceOver / Full Keyboard Access.
      .accessibilityHidden(isPresented)
      .overlay {
        ZStack {
          if isPresented {
            // Dimmed background that dismisses on tap. The barrier still covers the host; only the
            // paint is bounded, so click-outside-to-dismiss reaches every corner.
            ShellModalScrim(
              onTap: {
                log("DISMISSABLE_SHEET: Background tapped, dismissing")
                OmiMotion.withGated(.easeOut(duration: 0.2)) {
                  isPresented = false
                }
              }
            )
            .transition(.opacity)
            .zIndex(0)

            // Force the sheet into a centered full-size overlay so it
            // does not end up clipped or visually hidden behind the scrim.
            sheetContent()
              .background(Ink.surface)
              .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))
              .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
              .transition(.scale(scale: 0.95).combined(with: .opacity))
              .accessibilityAddTraits(.isModal)
              .zIndex(1)

            OverlayModalEscapeCatcher {
              log("DISMISSABLE_SHEET: Escape pressed, dismissing")
              OmiMotion.withGated(.easeOut(duration: 0.2)) {
                isPresented = false
              }
            }
            .zIndex(2)
          }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      .omiAnimation(.easeOut(duration: 0.2), value: isPresented)
  }
}

extension View {
  /// Presents a sheet that can be dismissed by clicking outside the content area.
  ///
  /// The dim bounds itself to whichever surface this sheet is mounted in — the enclosing
  /// `PageGlassLane` publishes that, so no call site chooses it. See `ShellModalScrim`.
  func dismissableSheet<Content: View>(
    isPresented: Binding<Bool>,
    @ViewBuilder content: @escaping () -> Content
  ) -> some View {
    self.modifier(DismissableSheetModifier(isPresented: isPresented, sheetContent: content))
  }

  /// Presents an item-based sheet that can be dismissed by clicking outside the content area.
  func dismissableSheet<Item: Identifiable, Content: View>(
    item: Binding<Item?>,
    @ViewBuilder content: @escaping (Item) -> Content
  ) -> some View {
    self.modifier(DismissableSheetItemModifier(item: item, sheetContent: content))
  }
}

/// Item-based version of DismissableSheetModifier for optional item bindings.
struct DismissableSheetItemModifier<Item: Identifiable, SheetContent: View>: ViewModifier {
  @Binding var item: Item?
  let sheetContent: (Item) -> SheetContent

  func body(content: Content) -> some View {
    content
      // The overlay is modal: while it is up, the content underneath must
      // not be reachable by VoiceOver / Full Keyboard Access.
      .accessibilityHidden(item != nil)
      .overlay {
        ZStack {
          if let presentedItem = item {
            // Dimmed background that dismisses on tap. The barrier still covers the host; only the
            // paint is bounded, so click-outside-to-dismiss reaches every corner.
            ShellModalScrim(
              onTap: {
                log("DISMISSABLE_SHEET: Background tapped, dismissing item")
                OmiMotion.withGated(.easeOut(duration: 0.2)) {
                  item = nil
                }
              }
            )
            .transition(.opacity)
            .zIndex(0)

            // Force the sheet into a centered full-size overlay so it
            // does not end up clipped or visually hidden behind the scrim.
            sheetContent(presentedItem)
              .background(Ink.surface)
              .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))
              .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
              .transition(.scale(scale: 0.95).combined(with: .opacity))
              .accessibilityAddTraits(.isModal)
              .zIndex(1)

            OverlayModalEscapeCatcher {
              log("DISMISSABLE_SHEET: Escape pressed, dismissing item")
              OmiMotion.withGated(.easeOut(duration: 0.2)) {
                item = nil
              }
            }
            .zIndex(2)
          }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      .omiAnimation(.easeOut(duration: 0.2), value: item?.id != nil)
  }
}
