import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// The search's filter menu: starred, one person, a date range (Flutter's starred and people tiles
/// and date filter).
struct SearchFilterMenu: View {
    @Environment(SettingsStore.self) private var settings
    let search: SearchStore
    @Binding var pickingDates: Bool

    var body: some View {
        Menu {
            Toggle(isOn: Binding(get: { search.filter.starred }, set: { search.filter.starred = $0 })) {
                Label(L("starred"), systemImage: "star")
            }
            if !settings.people.isEmpty {
                Menu {
                    ForEach(settings.people) { person in
                        Button {
                            search.filter.person = search.filter.person?.id == person.id ? nil : person
                        } label: {
                            if search.filter.person?.id == person.id {
                                Label(person.name, systemImage: "checkmark")
                            } else {
                                Text(person.name)
                            }
                        }
                    }
                } label: {
                    Label(L("people"), systemImage: "person.2")
                }
            }
            Section(L("filterByDate")) {
                Button { setDays(1) } label: { Text(L("today")) }
                Button { setDays(7) } label: { Text(L("nativeLast7Days")) }
                Button { setDays(30) } label: { Text(L("nativeLast30Days")) }
                Button { pickingDates = true } label: { Label(L("nativeChooseDates"), systemImage: "calendar") }
            }
            if search.filter.isActive {
                Button(role: .destructive) { search.filter = .init() } label: { Label(L("nativeClearFilters"), systemImage: "xmark") }
            }
        } label: {
            Image(systemName: search.filter.isActive ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle")
        }
        .accessibilityLabel(L("filters"))
        .accessibilityIdentifier("search.filters")
    }

    /// Today counts from midnight; longer ranges end now.
    private func setDays(_ days: Int) {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: .now)
        search.filter.start = calendar.date(byAdding: .day, value: 1 - days, to: today)
        search.filter.end = nil
    }
}

/// A removable filter capsule above the results.
struct FilterChip: View {
    let title: String
    let symbol: String
    let onRemove: () -> Void

    var body: some View {
        Button(action: onRemove) {
            HStack(spacing: DS.Spacing.xs) {
                Image(systemName: symbol)
                Text(title).lineLimit(1)
                Image(systemName: "xmark").font(.caption2.weight(.bold))
            }
            .font(.footnote.weight(.semibold))
            .foregroundStyle(DS.Palette.onAccent)
            .padding(.horizontal, DS.Spacing.md)
            .frame(minHeight: 32)
            .background(DS.Palette.accent, in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(L("nativeRemoveFilter", title))
    }
}

/// Pick a from–to range of days.
struct DateRangeSheet: View {
    @Environment(\.dismiss) private var dismiss
    let search: SearchStore
    @State private var start = Calendar.current.date(byAdding: .day, value: -7, to: .now) ?? .now
    @State private var end = Date.now

    var body: some View {
        NavigationStack {
            Form {
                DatePicker(L("nativeFrom"), selection: $start, in: ...end, displayedComponents: .date)
                DatePicker(L("nativeTo"), selection: $end, in: start..., displayedComponents: .date)
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(L("filterByDate"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("nativeApply")) {
                        let calendar = Calendar.current
                        search.filter.start = calendar.startOfDay(for: start)
                        search.filter.end = calendar.date(byAdding: DateComponents(day: 1, second: -1), to: calendar.startOfDay(for: end))
                        dismiss()
                    }
                }
            }
            .onAppear {
                if let chosen = search.filter.start { start = chosen }
                if let chosen = search.filter.end { end = chosen }
            }
        }
    }

    /// "Oct 1 – Oct 7", "Since Oct 1", or nil without a range.
    static func title(_ filter: SearchStore.Filter) -> String? {
        let format = Date.FormatStyle(date: .abbreviated, time: .omitted)
        switch (filter.start, filter.end) {
        case let (start?, end?): return "\(start.formatted(format)) – \(end.formatted(format))"
        case let (start?, nil): return L("nativeSinceDate", start.formatted(format))
        case let (nil, end?): return L("nativeUntilDate", end.formatted(format))
        default: return nil
        }
    }
}
