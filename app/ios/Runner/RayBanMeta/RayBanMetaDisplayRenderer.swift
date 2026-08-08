import Foundation

#if canImport(MWDATDisplay)
    import MWDATDisplay

    /// Translates the platform-neutral HUD screen into Meta's Display views.
    ///
    /// This file deliberately does not import SwiftUI: MWDATDisplay exports its
    /// own `Text`, `Button`, and `Image`, and importing both makes those names
    /// ambiguous (Meta documents this in the 0.7.0 release notes).
    enum RayBanMetaDisplayRenderer {
        static func flexBox(
            for screen: HudScreenWire,
            onAction: @escaping @Sendable (String) -> Void
        ) -> FlexBox {
            let lines = screen.lines
            let actions = screen.actions
            let title = screen.title

            return FlexBox(direction: .column, spacing: 12) {
                FlexBox(direction: .column, spacing: 4) {
                    Text(title, style: .heading)
                    for line in lines {
                        Text(line.text, style: textStyle(for: line.style), color: line.muted ? .secondary : .primary)
                    }
                }
                .padding(24)
                .background(.card)

                if !actions.isEmpty {
                    FlexBox(direction: .row, spacing: 8, alignment: .center, crossAlignment: .center, wrap: true) {
                        for action in actions {
                            Button(label: action.label, onClick: { onAction(action.id) })
                        }
                    }
                }
            }
        }

        private static func textStyle(for style: String) -> TextStyle {
            switch style {
            case "heading": return .heading
            case "meta": return .meta
            default: return .body
            }
        }
    }
#endif
