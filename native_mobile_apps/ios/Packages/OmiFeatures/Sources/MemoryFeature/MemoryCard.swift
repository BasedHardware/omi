import Foundation
import OmiComponents
import OmiCore
import OmiDesign
import SwiftUI

/// Labels for Flutter's three memory kinds; any other (older) category shows as written.
enum MemoryKind {
    static func title(_ category: String) -> String {
        switch category {
        case "system": L("nativeMemoryKindAboutYou")
        case "interesting": L("filterInteresting")
        case "manual": L("filterManual")
        default: category.capitalized
        }
    }

    /// Where it was captured (Flutter `ClientDeviceService.deviceProvenanceType`): this iPhone,
    /// another iPhone, a Mac or an Android phone. `nil` when unknown.
    static func device(_ captureDevice: String?) -> (title: String, symbol: String)? {
        guard let captureDevice else { return nil }
        if let hash = UserDefaults.standard.string(forKey: "flutter.deviceIdHash"), captureDevice == "ios_\(hash)" {
            return (L("memoryThisIphone"), "iphone")
        }
        switch captureDevice.split(separator: "_").first {
        case "ios": return (L("memoryProvenanceIphone"), "iphone")
        case "macos": return (L("memoryProvenanceMac"), "laptopcomputer")
        case "android": return (L("memoryProvenanceAndroid"), "smartphone")
        default: return nil
        }
    }
}

/// One memory as a quiet row: its text, then kind and date (pin and visibility marks). The
/// conversation it came from opens from the long-press menu; new memories are reviewed from the
/// one entry at the top, never on the row.
struct MemoryCard: View {
    let memory: Memory
    let source: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                Text(memory.content)
                    .font(DS.Typography.cardTitle)
                    .foregroundStyle(DS.Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if memory.isBaseline {
                    Image(systemName: "pin")
                        .font(.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .accessibilityLabel(L("baselineMemory"))
                }
            }
            meta
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, DS.Spacing.md)
        .accessibilityElement(children: .combine)
        .accessibilityHint(source.map { L("nativeFromConversation", $0) } ?? "")
    }

    private var meta: some View {
        HStack(spacing: DS.Spacing.xs) {
            Text("\(MemoryKind.title(memory.category)) · \(memory.createdAt.formatted(date: .abbreviated, time: .omitted))")
            if memory.visibility == .public {
                Image(systemName: "globe").accessibilityLabel(L("nativeMemoryPublic"))
            }
            if let device = MemoryKind.device(memory.captureDevice) {
                Text(verbatim: "·")
                Label(device.title, systemImage: device.symbol).labelStyle(.titleAndIcon)
            }
        }
        .font(DS.Typography.caption)
        .foregroundStyle(DS.Palette.inkSecondary)
        .lineLimit(1)
    }
}
