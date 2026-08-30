//
//  SpineRibbon.swift — every loaded day as one strip, drawn once.
//
//  The rail beside the spine used to be twenty-four bars belonging to whichever day the top row was
//  in, and it **swapped** when the top row crossed midnight: the whole column's contents changed at
//  once, so a continuous scroll produced a discontinuous rail. The list next to it never does that —
//  it runs through the day boundary like the boundary is just another row — and a navigator that
//  jumps beside a list that flows is a navigator nobody reads as position.
//
//  So the ribbon is one strip: every loaded day, newest at the top, each day's hours running 23 → 0
//  the same direction the list runs, separated by a labelled break rather than a cut. The reading
//  position is a **fixed marker** and the strip slides under it, which is the only arrangement that
//  survives more days than fit on screen.
//
//  **Compact, not calendar-scaled.** A day with nothing in it is not drawn at all. Ribbon length is
//  therefore proportional to how much history is loaded, never to elapsed time — a quiet fortnight
//  is not a fortnight of empty strip to wheel past.
//
//  Drawn in a `Canvas` because at a few hundred days this is tens of thousands of bars, and a
//  `VStack` of them is tens of thousands of view identities re-evaluated on every scroll tick. Only
//  the days inside the viewport are drawn (`SpineRibbonGeometry.visibleDays`), so the cost is the
//  window, not the corpus.
//

import OmiTheme
import SwiftUI

// MARK: - Geometry

/// Where a moment in time lands on the strip. Pure arithmetic, no view — this is the part a test can
/// hold, and the part the wheel, the marker and the day breaks all have to agree about.
enum SpineRibbonGeometry {
  /// The band between two days, carrying the hairline and the day's name.
  static let dayBreakHeight: CGFloat = 20

  /// **One day is exactly one column.** The rail this replaced sized its twenty-four bars with
  /// `maxHeight: .infinity`, so a day filled whatever height the column had; keeping that means the
  /// strip looks like the rail always did and the only thing that changed is that it no longer ends
  /// at midnight. It also keeps the ribbon adaptive: a taller window gets a taller day, never a
  /// tighter one, and no hour spacing is baked into a constant that was right on one screen.
  static func dayHeight(viewport: CGFloat) -> CGFloat { max(dayBreakHeight + 24, viewport) }

  /// One hour, at that size.
  static func hourHeight(viewport: CGFloat) -> CGFloat {
    (dayHeight(viewport: viewport) - dayBreakHeight) / 24
  }

  /// How far down the ribbon's viewport the reading marker sits.
  ///
  /// Not at the very top: the strip above the marker is the part already read, and a navigator that
  /// shows none of where you came from is a progress bar. Not the middle either — the list's own
  /// reading line is near its top, and the two should roughly agree.
  static let markerFraction: CGFloat = 0.34

  /// Distance from the top of the whole strip to a moment, in points.
  ///
  /// Hours run **backwards** inside a day — hour 23 at the top — because the spine is newest-first
  /// and a rail ascending beside a descending list is the disagreement this file exists to remove.
  /// Minutes run backwards within the hour for the same reason: 23:59 sits at the very top of its
  /// day, 00:00 at the very bottom.
  static func depth(dayIndex: Int, hour: Int, minute: Int, viewport: CGFloat) -> CGFloat {
    let withinDay = (24 - CGFloat(hour) - CGFloat(minute) / 60) * hourHeight(viewport: viewport)
    return CGFloat(dayIndex) * dayHeight(viewport: viewport) + dayBreakHeight + withinDay
  }

  /// Which day and hour sit at a point on the strip — the inverse of `depth`.
  ///
  /// The reading position is continuous, so the hour to draw heavier is the one the marker is
  /// *inside*, not the hour of whichever row last reported. Deriving it from the same number that
  /// positions the strip is what stops the heavy bar from ever being a bar other than the one under
  /// the marker.
  static func marker(atDepth depth: CGFloat, viewport: CGFloat) -> (dayIndex: Int, hour: Int) {
    let day = dayHeight(viewport: viewport)
    let dayIndex = max(0, Int((depth / day).rounded(.down)))
    let withinDay = depth - CGFloat(dayIndex) * day - dayBreakHeight
    let hour = 24 - withinDay / hourHeight(viewport: viewport)
    return (dayIndex, min(23, max(0, Int(hour.rounded(.down)))))
  }

  /// The days with any part inside a viewport of `height` reading at `depth`.
  ///
  /// Empty when there is nothing loaded, and clamped to the ends: scrolling past the newest or the
  /// oldest day is a strip that runs out, not an index that goes negative.
  static func visibleDays(depth: CGFloat, height: CGFloat, count: Int) -> Range<Int> {
    guard count > 0, height > 0 else { return 0..<0 }
    let day = dayHeight(viewport: height)
    let top = depth - height * markerFraction
    let first = max(0, Int((top / day).rounded(.down)))
    let last = min(count - 1, Int(((top + height) / day).rounded(.down)))
    guard first <= last else { return 0..<0 }
    return first..<(last + 1)
  }
}

// MARK: - One day's worth of strip

/// What the ribbon needs to draw a day: who it is, what to call the break above it, and its shape.
struct SpineRibbonDay: Equatable, Identifiable {
  let id: Date
  let title: String
  /// 24 values, indexed by hour, each 0…1 against that day's own busiest hour — the same
  /// per-day normalisation `SpineStore.density(for:)` documents. Scaling every day against a
  /// record-breaking one months ago would flatten every ordinary day into a straight line, and that
  /// is no less true now that the days are drawn end to end.
  let density: [Double]

  func weight(_ hour: Int) -> Double { density.indices.contains(hour) ? density[hour] : 0 }
}

// MARK: - The strip

/// The strip itself, sliding under a fixed marker.
///
/// `Animatable` on the depth, so a scroll that moves the anchor nine hours in one step glides there
/// instead of teleporting. Interpolating the value the `Canvas` reads is the only way to animate a
/// `Canvas` at all — there is no view whose frame is changing for `.animation` to work on.
struct SpineRibbon: View, Animatable {
  /// Every loaded day, newest first.
  let days: [SpineRibbonDay]
  /// Where the marker is reading, in strip points. See `SpineRibbonGeometry.depth`.
  var depth: CGFloat
  /// Whether any hour is lit at all. `false` before the list has reported a row — every day folded
  /// shut, or nothing read yet — where the strip still parks somewhere but nothing on it is being
  /// read. Which hour is lit is not passed in: it is derived from `depth`, so it cannot disagree
  /// with where the strip actually sits.
  let highlightsMarker: Bool

  /// `nonisolated` because `Animatable` is: SwiftUI interpolates this off the view's own isolation.
  /// Safe here because everything it touches is a `Sendable` value.
  nonisolated var animatableData: CGFloat {
    get { depth }
    set { depth = newValue }
  }

  /// A bar this fraction of its day's peak or more is drawn heavier. One ink at three weights, like
  /// every other ranking in this system.
  private static let hotThreshold = 0.6
  /// The bar's own metrics, unchanged from the per-day rail: the shortest a bar is ever drawn (an
  /// hour with nothing in it is still an hour, and a gap would read as the rail having ended), and
  /// how much the busiest hour adds to it.
  private static let minimumBarWidth: CGFloat = 14
  private static let maximumBarExtra: CGFloat = 78
  /// The gap between a bar and its caption. The caption follows the bar rather than sitting in a
  /// fixed column, which is how the rail has always drawn it.
  private static let captionGap: CGFloat = 7
  /// How far into the break band the hairline sits, leaving the day's name room underneath.
  private static let breakRuleOffset: CGFloat = 4

  /// Hours named on every day, so the strip stays readable without becoming an axis.
  private nonisolated static let labelledHours: Set<Int> = [0, 6, 12, 18]

  var body: some View {
    Canvas(opaque: false, rendersAsynchronously: false) { context, size in
      draw(in: &context, size: size)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .accessibilityHidden(true)
  }

  private func draw(in context: inout GraphicsContext, size: CGSize) {
    // Where the reading position sits in the column. **Nothing is drawn here** — the hour under it
    // is already the one heavy, named bar on the strip, and a second mark saying the same thing
    // twice is the stray-scrollbar look the per-day rail removed once already.
    let translate = size.height * SpineRibbonGeometry.markerFraction - depth
    let dayHeight = SpineRibbonGeometry.dayHeight(viewport: size.height)
    let hourHeight = SpineRibbonGeometry.hourHeight(viewport: size.height)
    let marker = SpineRibbonGeometry.marker(atDepth: depth, viewport: size.height)
    let window = SpineRibbonGeometry.visibleDays(
      depth: depth, height: size.height, count: days.count)

    for index in window {
      let day = days[index]
      let dayTop = translate + CGFloat(index) * dayHeight
      // No break above the newest day: the strip starts there, it does not resume there.
      if index > 0 { drawBreak(&context, day: day, top: dayTop, width: size.width) }
      let litHour = highlightsMarker && index == marker.dayIndex ? marker.hour : nil
      for hour in SpineHourRail.renderedHours {
        drawBar(
          &context, day: day, hour: hour, litHour: litHour, dayTop: dayTop, hourHeight: hourHeight,
          height: size.height)
      }
    }
  }

  /// The hairline sits high in the band and the name hangs **below** it.
  ///
  /// Both parts are load-bearing. The day above ends with its midnight hour, which is captioned
  /// "12 AM" — a name drawn level with the rule lands on that caption, which is what the first
  /// version did. Below the rule the band is empty until the next day's 11 PM bar, so the name has
  /// the width of the column to itself and clearly belongs to the day starting under it rather than
  /// the one ending over it.
  private func drawBreak(
    _ context: inout GraphicsContext, day: SpineRibbonDay, top: CGFloat, width: CGFloat
  ) {
    let ruleY = top + Self.breakRuleOffset
    context.fill(
      Path(CGRect(x: 0, y: ruleY, width: width, height: 1)),
      with: .color(Ink.separator))
    guard let label = SpineHourRail.headlineScope(day.title) else { return }
    let text =
      Text(label.uppercased())
      .font(.system(size: 8, weight: .semibold))
      .tracking(0.7)
      .foregroundStyle(Ink.secondary)
    context.draw(text, at: CGPoint(x: 0, y: ruleY + 3), anchor: .topLeading)
  }

  private func drawBar(
    _ context: inout GraphicsContext, day: SpineRibbonDay, hour: Int, litHour: Int?,
    dayTop: CGFloat, hourHeight: CGFloat, height: CGFloat
  ) {
    let slotTop = dayTop + SpineRibbonGeometry.dayBreakHeight + CGFloat(23 - hour) * hourHeight
    let centerY = slotTop + hourHeight / 2
    // Off the top or bottom of the column: nothing to draw, and skipping it here is what keeps a
    // redraw proportional to what is actually on screen.
    guard centerY > -hourHeight, centerY < height + hourHeight else { return }

    let weight = day.weight(hour)
    let isCurrent = hour == litHour
    let barHeight: CGFloat = isCurrent ? 6 : 5
    let barWidth = Self.minimumBarWidth + CGFloat(weight) * Self.maximumBarExtra
    let opacity = isCurrent ? 0.85 : (weight >= Self.hotThreshold ? 0.42 : 0.2)
    context.fill(
      Path(
        roundedRect: CGRect(x: 0, y: centerY - barHeight / 2, width: barWidth, height: barHeight),
        cornerRadius: barHeight / 2, style: .continuous),
      with: .color(Ink.primary.opacity(opacity)))

    guard let hourLabel = Self.caption(for: hour, isLit: isCurrent) else { return }
    let text =
      Text(hourLabel)
      .font(.system(size: 9, weight: isCurrent ? .semibold : .regular))
      .tracking(0.6)
      .foregroundStyle(isCurrent ? Ink.primary : Ink.secondary)
    context.draw(
      text, at: CGPoint(x: barWidth + Self.captionGap, y: centerY), anchor: .leading)
  }

  /// Which hours say their name.
  ///
  /// **Exactly the rule the per-day rail has always used**: the four fixed hours orient every day
  /// without turning the strip into an axis, and the hour being read names itself when it is not one
  /// of them. Nothing is suppressed. An earlier version here dropped a fixed label within an hour of
  /// the marker, to stop two captions colliding — a real collision, but only at the six-point hour
  /// spacing that version drew at. At one day per column an hour is more than twenty points and the
  /// two captions never touch, so the rule was deleting labels to prevent an overlap that cannot
  /// happen, and made the strip read differently from the rail it replaced.
  nonisolated static func caption(for hour: Int, isLit: Bool) -> String? {
    if labelledHours.contains(hour) { return SpineFormat.hourLabel(hour) }
    return isLit ? SpineFormat.hourLabel(hour) : nil
  }
}
