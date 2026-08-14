//
//  ActivityHourRail.swift — the day as a shape you can aim at.
//
//  Twenty-four bars, one per hour, **late night at the top and midnight at the bottom**. That is the
//  whole point of the file. The list is newest-first, so an *ascending* rail beside it — the obvious
//  way to draw a day — would put 6 AM at the top of a column whose top row is 11 PM, and the two
//  would disagree about which way time runs. That mismatch is the thing most timeline UIs ship, and
//  it is why nobody trusts the scrubber next to their feed.
//
//  The highlight tracks the hour of the **topmost visible row**, not a fraction of the scroll.
//  Scroll percentage is a lie about a list whose rows are different heights: a day of one
//  conversation and a day of forty occupy the same rail at the same speed. Reading the row that is
//  actually under the header means the marker says the hour you are looking at, which is the only
//  thing it could usefully say.
//
//  Brand: `Ink` semantics only, two rungs (glass) — the rail is one ink at three weights, never a
//  hue (INV-UI-1).
//

import AppKit
import SwiftUI

struct ActivityHourRail: View {
    /// One entry per hour, indexed 0…23, each 0…1 against the day's own busiest hour.
    let density: [Double]
    /// The hour under the top of the list, or nil before anything has been read.
    let currentHour: Int?
    /// The headline: how much screen capture the day being read holds, or `nil` while that day is
    /// still being read. `nil` is not zero — see `headlineCaption`.
    let momentCount: Int?
    /// Which day all of the above is about — "Today", "Yesterday", "Wednesday 6 August".
    let dayTitle: String
    /// The footer: what else that day held.
    let conversationCount: Int

    /// **The order the bars are drawn in, and the whole point of this file:** latest hour first, so
    /// the rail runs the same direction as the newest-first list beside it. A value rather than a
    /// `stride` buried in a `ForEach`, because it is the one thing here a test can hold.
    nonisolated static let renderedHours: [Int] = Array(stride(from: 23, through: 0, by: -1))

    /// The width every line in this column has to live inside. A named value rather than a literal
    /// in the `frame`, so the copy below can be measured against the column it actually gets.
    nonisolated static let contentWidth: CGFloat = 154

    /// One point of the column held back from the fit test.
    ///
    /// `Text` lays out with SwiftUI's typesetter and `scopeWidth` measures with `NSString.size`; they
    /// agree to well under a point, but a form measuring *exactly* the column width is a coin flip on
    /// whether it wraps. A point of margin removes the coin flip and costs a handful of extra
    /// shortened forms.
    private nonisolated static let scopeFitBudget: CGFloat = contentWidth - 1

    /// Labelled hours. Four is enough to orient without turning the rail into an axis.
    static let labelledHours: Set<Int> = [0, 6, 12, 18]

    /// A bar this fraction of the peak or more is drawn heavier. Not a hue — the rail is one ink at
    /// two weights, like every other ranking in this system.
    static let hotThreshold = 0.6

    /// Below this the rail is dropped rather than squeezed: a rail narrower than its own hour labels
    /// is a column of stubs, and the list is the part worth the width.
    static let breakpoint: CGFloat = 620

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Number, noun, day — "0 screen moments, Yesterday", read straight down. The day goes
            // last so nothing on the rail shares a baseline with the list's own pinned day header,
            // which prints the same word in caps a short distance to the right.
            VStack(alignment: .leading, spacing: 2) {
                Text(Self.headlineNumber(momentCount))
                    .inkStyle(.stepHeadline, color: Ink.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(Self.headlineCaption(momentCount))
                    .inkStyle(.statusLabel, color: Ink.secondary)
                if let scope = Self.headlineScope(dayTitle) {
                    Text(scope)
                        .inkStyle(.statusLabel, color: Ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            bars

            if let footer = Self.footer(conversationCount: conversationCount) {
                Text(footer)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(width: Self.contentWidth, alignment: .leading)
        .padding(.horizontal, 14)
        .padding(.vertical, 16)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            Text(
                Self.readAloud(
                    momentCount: momentCount,
                    dayTitle: dayTitle,
                    conversationCount: conversationCount,
                    currentHour: currentHour)))
    }

    /// **The rail counts one day of screen capture, and it has to say so in its own words.**
    ///
    /// A day that has not been read yet is indistinguishable in the store from a day with nothing
    /// on it, and a rail that printed a confident `0` for a day it had not looked at is a rail
    /// making a claim about the machine it has no evidence for. `nil` means "not read yet" and says
    /// so; `0` means the read came back empty, which is a claim the rail is entitled to make.
    nonisolated static func headlineCaption(_ count: Int?) -> String {
        guard let count else { return "counting screen moments" }
        return count == 1 ? "screen moment" : "screen moments"
    }

    /// The day the headline number belongs to — the rail's half of "state your own scope".
    ///
    /// **On its own line it still has to fit, and unshortened it does not.** `ActivityFormat.day`
    /// emits `EEEE d MMMM yyyy` for a day outside the current year, and its widest output —
    /// "Wednesday 30 September 2026", 183 pt — overhangs this 154 pt column by 29 pt. A scope that
    /// wraps orphans "Wednesday 30" directly above the bars, where a bare number-and-word line reads
    /// as another count. So when the full title does not fit, the **weekday is dropped**: it is the
    /// one word carrying nothing the rest of the line does not already say, the date alone identifies
    /// the day completely, and the list header to the right is still printing the day in full.
    ///
    /// Measured against the column rather than reasoned about from an example date, so a change to
    /// the day format cannot quietly put the line back over the edge.
    ///
    /// `nil` when there is no day yet: an empty capture has no scope to claim, and inventing one
    /// would be the confident-zero mistake in a second place.
    nonisolated static func headlineScope(_ dayTitle: String) -> String? {
        let trimmed = dayTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        guard scopeWidth(trimmed) > scopeFitBudget else { return trimmed }

        let words = trimmed.split(separator: " ")
        guard words.count > 1 else { return trimmed }
        let withoutWeekday = words.dropFirst().joined(separator: " ")
        // Only if it actually bought a fitting line. A form no shortening can save keeps its full
        // text and wraps — a wrapped day is bad, a silently wrong day is worse.
        return scopeWidth(withoutWeekday) <= scopeFitBudget ? withoutWeekday : trimmed
    }

    /// The width `statusLabel` — the role both of the rail's secondary lines use — draws `text` at.
    ///
    /// Resolved through `InkFonts.role`, the same path `.inkStyle(.statusLabel, …)` takes, so the
    /// measurement cannot drift from the drawing if that role's size or face ever moves.
    nonisolated static func scopeWidth(_ text: String) -> CGFloat {
        let metrics = InkFonts.role(size: InkType.statusLabel.size, weight: .regular).metrics
        return (text as NSString).size(withAttributes: [.font: metrics]).width
    }

    /// An em dash rather than a `0` for the uncounted case: a placeholder that cannot be misread as
    /// a measurement.
    nonisolated static func headlineNumber(_ count: Int?) -> String {
        guard let count else { return "—" }
        return ActivityFormat.number(count)
    }

    /// What else the day held. `nil` rather than an empty string when the day holds no
    /// conversations, so the rail drops the line instead of drawing a blank one and speaking a
    /// sentence with a hole in it.
    nonisolated static func footer(conversationCount: Int) -> String? {
        guard conversationCount > 0 else { return nil }
        return ActivityFormat.plural(conversationCount, "conversation", "conversations")
    }

    /// The whole rail as one spoken sentence, because the whole rail is one accessibility element.
    ///
    /// **The scope leads here while it trails on screen, deliberately.** Speech has no baselines to
    /// collide on and no grouping either: a listener gets one linear sentence with no way to glance
    /// back, so the scope has to frame the number before the number arrives — "Today: 0 screen
    /// moments", not a number that turns out three clauses later to have been about a particular
    /// day.
    nonisolated static func readAloud(
        momentCount: Int?,
        dayTitle: String,
        conversationCount: Int,
        currentHour: Int?
    ) -> String {
        // The em dash is a visual placeholder; spoken, it has to be the sentence it stands for.
        let count =
            momentCount == nil
            ? "Counting screen moments"
            : "\(headlineNumber(momentCount)) \(headlineCaption(momentCount))"
        var text = headlineScope(dayTitle).map { "\($0): \(count)." } ?? "\(count)."
        if let footer = footer(conversationCount: conversationCount) { text += " \(footer)." }
        if let currentHour { text += " Reading \(ActivityFormat.hourLabel(currentHour))." }
        return text
    }

    /// The bars themselves, drawn 23 → 0 top to bottom.
    private var bars: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Self.renderedHours, id: \.self) { hour in
                let weight = density.indices.contains(hour) ? density[hour] : 0
                ActivityHourBar(
                    hour: hour,
                    weight: weight,
                    isHot: weight >= Self.hotThreshold,
                    isCurrent: hour == currentHour,
                    label: Self.labelledHours.contains(hour)
                        ? ActivityFormat.hourLabel(hour) : nil
                )
                .frame(maxHeight: .infinity)
            }
        }
        .frame(maxHeight: .infinity)
    }
}

/// One hour.
struct ActivityHourBar: View {
    let hour: Int
    let weight: Double
    let isHot: Bool
    let isCurrent: Bool
    let label: String?

    /// The shortest a bar is ever drawn. An hour with nothing in it is still an hour, and a gap in
    /// the column would read as the rail having ended.
    static let minimumWidth: CGFloat = 14
    static let maximumExtra: CGFloat = 78
    static let height: CGFloat = 5
    static let currentHeight: CGFloat = 6

    /// The three weights the rail ranks with. **The marker is the bar itself, not a band behind
    /// it**: a full-width wash across the current row reads as a stray scrollbar — a long dark rule
    /// among short pale pills looks like chrome that escaped, not like "you are here". The current
    /// hour is simply the darkest bar with its hour named beside it, which is how every other
    /// ranking in this system is drawn.
    static let restOpacity = 0.2
    static let hotOpacity = 0.42
    static let currentOpacity = 0.85

    private var caption: String? {
        if let label { return label }
        return isCurrent ? ActivityFormat.hourLabel(hour) : nil
    }

    var body: some View {
        HStack(spacing: 7) {
            Capsule()
                .fill(
                    Ink.primary.opacity(
                        isCurrent
                            ? Self.currentOpacity : (isHot ? Self.hotOpacity : Self.restOpacity))
                )
                .frame(
                    width: Self.minimumWidth + CGFloat(weight) * Self.maximumExtra,
                    height: isCurrent ? Self.currentHeight : Self.height)
            if let caption {
                Text(caption)
                    .font(.system(size: 9, weight: isCurrent ? .semibold : .regular))
                    .tracking(0.6)
                    .foregroundStyle(isCurrent ? Ink.primary : Ink.secondary)
                    .lineLimit(1)
                    .fixedSize()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
