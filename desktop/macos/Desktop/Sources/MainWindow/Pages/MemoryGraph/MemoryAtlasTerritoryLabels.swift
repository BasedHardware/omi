import AppKit
import OmiSupport
import OmiTheme
import SwiftUI

// The territory layer's own vocabulary: whether a point is ashore, what a
// caption is allowed to say, where it may sit, and what Escape takes back.
// Split out of the atlas view because none of it needs the view — it is
// geometry and policy the view asks questions of, and it was the largest
// single reason that file kept growing.
/// Whether a point in normalized map space falls on a territory.
///
/// Even-odd, so a ring enclosed by another counts as the hole it is.
func memoryAtlasCoastlineContains(_ rings: [[CGPoint]], _ point: CGPoint) -> Bool {
  var inside = false
  for ring in rings where ring.count >= 3 {
    var previous = ring[ring.count - 1]
    for current in ring {
      if (current.y > point.y) != (previous.y > point.y) {
        let t = (point.y - current.y) / (previous.y - current.y)
        if point.x < current.x + t * (previous.x - current.x) { inside.toggle() }
      }
      previous = current
    }
  }
  return inside
}

/// Makes a region's name look pressable before it is pressed.
///
/// Set quietly enough to be a map label rather than a control — which is what
/// it should look like at rest — a caption gives a sighted user no reason to
/// think it does anything. Hover is where that gets said: the label lifts to
/// full contrast and grows a scope, the same glyph the inspector's Focus
/// control uses for the same act.
struct MemoryAtlasNeighbourhoodCaption: View {
  let caption: String
  let size: CGSize
  let enter: () -> Void

  @State private var isHovered = false

  var body: some View {
    Button(action: enter) {
      HStack(spacing: 5) {
        // Set in tracked upper case, the way an atlas sets a country against
        // the towns inside it. Without that, a region's name is the same
        // treatment as an entity's own, in a pill bigger than any node — so it
        // reads as a very important entity rather than as the ground they
        // stand on, and "Omi · pull request · GitHub" competes with the Omi
        // and GitHub labels a few points away instead of describing them.
        Text(caption.uppercased())
          .scaledFont(size: 9, weight: .semibold)
          .tracking(0.8)
          .foregroundColor(isHovered ? Ink.primary : Ink.secondary)
          .lineLimit(1)
          .truncationMode(.tail)

        Image(systemName: "scope")
          .scaledFont(size: 8, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .opacity(isHovered ? 1 : 0)
          .frame(width: isHovered ? 9 : 0)
      }
      .padding(.horizontal, 9)
      // Sized to the box the placement pass reserved. Left to size itself, a
      // caption grows past the width its collision test assumed and starts
      // covering the neighbouring regions it was measured against.
      .frame(width: size.width, height: size.height)
      // A scrim, because the caption sits over the map rather than beside it
      // and the dots underneath would read through the letters.
      .background(
        Capsule()
          .fill(Ink.surface.opacity(isHovered ? 0.92 : 0.66))
          .overlay(
            Capsule().stroke(Ink.separator.opacity(isHovered ? 0.4 : 0.14), lineWidth: 1))
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    // Quiet enough at rest to be a map label rather than a control, which is
    // what it should look like — so hover is where "this does something" gets
    // said. The scope is the glyph the inspector's Focus control already uses
    // for the same act.
    .onHover { hovering in
      withAnimation(OmiMotion.gated(.easeOut(duration: 0.12))) { isHovered = hovering }
    }
  }
}

/// What Escape undoes on the Brain Map, one layer at a time.
///
/// The map stacks modes: you go into a place, pick something inside it, then
/// search from there. Collapsing all of that on one press throws away two
/// decisions the user did not ask to undo — and the version that cleared only
/// the search and the selection left the newest mode as the only one with no
/// keyboard way out, which is exactly backwards.
///
/// Innermost first, and nothing at all once there is nothing left: the press
/// then belongs to whatever is around the map. Escape backing out of a page is
/// how the rest of this app behaves, and a map that swallows the key
/// unconditionally is a page you can only leave with the mouse.
enum MemoryAtlasDismissal {
  enum Step: Equatable {
    case search
    /// One hop back along the trail of entities the user followed. Their own
    /// pushes, so their own pops — dropping the whole trail on one press would
    /// throw away every step of a walk five relationships deep.
    case selectionStep
    case selection
    case neighbourhood
    /// Nothing to undo — the key is not the map's to eat.
    case passThrough
  }

  static func next(
    isSearching: Bool, hasSelection: Bool, hasTrail: Bool, isInsideNeighbourhood: Bool
  ) -> Step {
    if isSearching { return .search }
    if hasSelection { return hasTrail ? .selectionStep : .selection }
    if isInsideNeighbourhood { return .neighbourhood }
    return .passThrough
  }
}

/// Where a region's name goes, and whether it goes anywhere at all.
///
/// Separate from the drawing so the tap target and the painted caption are
/// computed once from the same geometry. A label you can see but not press —
/// or press somewhere it is not — is the classic failure of hit-testing a
/// canvas twice.
enum MemoryAtlasNeighbourhoodLabels {
  /// One island of one neighbourhood, on screen.
  ///
  /// The unit is the island rather than the neighbourhood because the island
  /// is the thing a person sees. A group that holds two separate pieces of
  /// ground used to get a single caption over one of them, which left the
  /// other drawn, outlined, and anonymous — an unexplained shape on the map.
  struct Island: Equatable {
    let regionID: Int
    let index: Int
    /// The coast, in normalized map coordinates. Projected at draw time rather
    /// than here, so the same ring survives a camera move.
    let ring: [CGPoint]
    /// Where it is on screen right now. The projected ring is kept so the
    /// caption placer can ask whether a point on the canvas is ashore without
    /// projecting all of it again for every candidate.
    let projected: [CGPoint]
    let bounds: CGRect
    let center: CGPoint
  }

  struct Placed: Equatable, Identifiable {
    let regionID: Int
    let index: Int
    let caption: String
    /// The painted and tappable box, in view coordinates.
    let rect: CGRect
    /// The one island this caption names.
    let ring: [CGPoint]

    var id: String { "\(regionID)-\(index)" }
  }

  /// Past this the captions are the map. Eight territories is already more
  /// than anyone holds in their head at a glance.
  static let limit = 8

  /// The smallest an island may look on screen and still be worth naming.
  ///
  /// Islands are drawn only when they are named, so this is also the smallest
  /// one the map draws — which is the point. A speck of territory the size of
  /// a couple of dots says nothing that the dots do not already say, and eight
  /// of them around the edge of a region read as noise around it.
  static let smallestNamed: CGFloat = 26

  /// Whether territories are the subject at this camera.
  ///
  /// Selecting an entity hands the map over to that entity's own
  /// neighbourhood, and a search filter is asking a different question
  /// entirely. Otherwise they stay: an earlier version dropped them past
  /// neighbourhood zoom, so zooming in on an island made it vanish — the one
  /// thing a person does after seeing a place they want to look at.
  ///
  /// Inside a place, none of that applies. The island the user went into is
  /// the frame everything else is being read in, so it outlasts zooming all
  /// the way in and picking an entity off it — both of which used to erase the
  /// only thing on screen saying where they were.
  static func areVisible(
    detailLevel: MemoryAtlasDetailLevel, hasSelection: Bool, isInsideNeighbourhood: Bool
  ) -> Bool {
    if isInsideNeighbourhood { return true }
    guard !hasSelection else { return false }
    return detailLevel != .inspect
  }

  /// The islands on screen, largest first, before anything is named.
  ///
  /// Separate from `place` so the map can decide which entity labels to
  /// suppress before it decides where captions go — otherwise a caption avoids
  /// an entity name that is about to be hidden, and gets pushed off its own
  /// island for nothing.
  static func islands(
    _ regions: [MemoryAtlasNeighbourhood],
    in size: CGSize,
    project: (CGPoint) -> CGPoint,
    focused: Int? = nil
  ) -> [Island] {
    let visible = CGRect(origin: .zero, size: size)
    var found: [Island] = []
    for region in regions where focused == nil || region.id == focused {
      for (index, ring) in region.coastline.enumerated() where ring.count >= 3 {
        let points = ring.map(project)
        var minimum = points[0]
        var maximum = points[0]
        for point in points {
          minimum = CGPoint(x: min(minimum.x, point.x), y: min(minimum.y, point.y))
          maximum = CGPoint(x: max(maximum.x, point.x), y: max(maximum.y, point.y))
        }
        let bounds = CGRect(
          x: minimum.x, y: minimum.y, width: maximum.x - minimum.x, height: maximum.y - minimum.y)
        guard bounds.intersects(visible) else { continue }
        guard max(bounds.width, bounds.height) >= smallestNamed || focused != nil else { continue }
        found.append(
          Island(
            regionID: region.id, index: index, ring: ring, projected: points, bounds: bounds,
            center: CGPoint(
              x: points.map(\.x).reduce(0, +) / CGFloat(points.count),
              y: points.map(\.y).reduce(0, +) / CGFloat(points.count))))
      }
    }
    // Biggest first, so a crowded viewport spends its captions on the places
    // that dominate it rather than on whichever region the detector numbered
    // lowest.
    return found.sorted {
      let mine = $0.bounds.width * $0.bounds.height
      let theirs = $1.bounds.width * $1.bounds.height
      return mine == theirs ? ($0.regionID, $0.index) < ($1.regionID, $1.index) : mine > theirs
    }
  }

  /// How far to zoom, and where to point, when the user enters a region.
  ///
  /// Framed so the region fills most of the viewport but not all of it — a
  /// neighbourhood you cannot see the edges of is indistinguishable from the
  /// whole map, which is what the user just left.
  static let enteredCoverage: CGFloat = 0.62

  static func entering(
    center: CGPoint,
    radius: CGFloat,
    viewport: CGSize,
    zoomRange: ClosedRange<CGFloat>
  ) -> (zoom: CGFloat, pan: CGSize) {
    let extent = max(radius * 2, 0.02)
    let zoom = min(max(enteredCoverage / extent, zoomRange.lowerBound), zoomRange.upperBound)
    // The same single scale the canvas projects with, so the region the camera
    // frames is the region the user is looking at.
    let span = MemoryAtlasLayoutEngine.projectionSpan(of: viewport)
    return (
      zoom,
      CGSize(
        width: (0.5 - center.x) * span * zoom,
        height: (0.5 - center.y) * span * zoom)
    )
  }

  /// The zoom at which zooming out counts as having left the place you went
  /// into.
  ///
  /// Relative to the camera that entering actually chose, never a constant.
  /// A big island is framed at a low zoom — sometimes below the fixed
  /// threshold this replaced — so entering it set a zoom that immediately read
  /// as "zoomed back out" and threw the user straight out again. Any island
  /// wider than about half the map was unenterable, which on an account with a
  /// handful of regions is all of them.
  ///
  /// The margin is what keeps a small zoom-out from being an exit: nudging the
  /// camera to see a little more context around a place is not leaving it.
  ///
  /// `nil` when the answer would sit below the map's own minimum zoom, which
  /// happens for a region so large that entering it barely moves the camera.
  /// There is no "further out" than the whole map, so a threshold down there is
  /// one that can never be crossed — it reads as a working exit and is not one.
  /// Saying so lets those places be left the two ways that do work: Escape, and
  /// pressing the caption again.
  static func departureZoom(
    enteredAt zoom: CGFloat, neighbourhoodZoom: CGFloat, minimumZoom: CGFloat
  ) -> CGFloat? {
    let departure = min(zoom, neighbourhoodZoom) * 0.85
    return departure > minimumZoom ? departure : nil
  }

  /// Zoom-out floor after Escape (or inspector close) has sent the camera
  /// home while the neighbourhood is still the next layer on the stack.
  ///
  /// The original threshold sits above zoom 1, so a selection-clear that
  /// resets the viewport would otherwise also end the island. Rebinding from
  /// the overview camera keeps that layer for the next Escape; a later
  /// pinch below this floor can still leave.
  static func overviewDepartureZoom(neighbourhoodZoom: CGFloat, minimumZoom: CGFloat) -> CGFloat? {
    departureZoom(enteredAt: 1, neighbourhoodZoom: neighbourhoodZoom, minimumZoom: minimumZoom)
  }

  /// Places on the island where its whole name would sit on land, nearest the
  /// middle first.
  ///
  /// The centroid is only a starting guess: a crescent or a two-lobed island
  /// has its centroid in the water, and a name centred there straddles the bay.
  /// So the candidates are ranked by distance from the centroid and each is
  /// checked properly — both ends of the label have to be ashore, or a long
  /// name hangs off a narrow island with most of itself over the sea.
  private static func interior(of island: Island, within reachable: CGRect, width: CGFloat)
    -> [CGPoint]
  {
    guard reachable.width > 8, reachable.height > 8 else { return [] }
    let half = width / 2
    var candidates: [(point: CGPoint, distance: CGFloat)] = []
    let steps = 6
    for row in 0...steps {
      for column in 0...steps {
        let point = CGPoint(
          x: reachable.minX + reachable.width * CGFloat(column) / CGFloat(steps),
          y: reachable.minY + reachable.height * CGFloat(row) / CGFloat(steps))
        candidates.append(
          (point, hypot(point.x - island.center.x, point.y - island.center.y)))
      }
    }
    candidates.sort { $0.distance < $1.distance }

    // The ring is in map coordinates and these points are on screen, so the
    // test runs the other way round: walk the projected ring once and reuse it.
    func ashore(_ point: CGPoint) -> Bool {
      var inside = false
      var previous = island.projected[island.projected.count - 1]
      for current in island.projected {
        if (current.y > point.y) != (previous.y > point.y) {
          let t = (point.y - current.y) / (previous.y - current.y)
          if point.x < current.x + t * (previous.x - current.x) { inside.toggle() }
        }
        previous = current
      }
      return inside
    }

    // Two tiers, and the second matters more than it looks. Requiring the whole
    // label to be ashore reads best but almost never fires: territories are
    // long and narrow far more often than they are round, so on a real account
    // only the two widest islands qualified and every other name went back to
    // floating above its coast. A name centred on its island, with the ends of
    // its capsule over water, still unmistakably belongs to it.
    let wholeLabelFits =
      candidates
      .filter {
        ashore($0.point) && ashore(CGPoint(x: $0.point.x - half, y: $0.point.y))
          && ashore(CGPoint(x: $0.point.x + half, y: $0.point.y))
      }
      .prefix(3).map(\.point)
    let centreIsAshore = candidates.filter { ashore($0.point) }.prefix(3).map(\.point)
    return wholeLabelFits + centreIsAshore
  }

  /// Names the islands, and reports only the ones it could name.
  ///
  /// The map draws exactly what comes back from here, so an island that cannot
  /// be given a caption is not drawn at all. That is the contract: a shape on
  /// this map always says what it is. The alternative — drawing the territory
  /// and dropping the caption when it does not fit — is what produced outlined
  /// regions with no explanation anywhere near them.
  static func place(
    _ islands: [Island],
    captions: [Int: String],
    in size: CGSize,
    /// Boxes already spoken for — the entity names the map is still drawing. A
    /// caption laid over one of those replaces a fact with a summary.
    avoiding taken: [CGRect] = [],
    limit: Int = limit,
    /// Whether every island passed in must come back named.
    ///
    /// Off for the overview, where the map is choosing which places to show and
    /// declining to draw one it cannot label is the right answer. On once the
    /// user has gone into a place: they asked for that island specifically, and
    /// leaving them on an empty canvas because its name collided with an entity
    /// label answers a question nobody asked.
    insisting: Bool = false
  ) -> [Placed] {
    var placed: [Placed] = []
    var occupied = taken
    let visible = CGRect(origin: .zero, size: size)

    for island in islands where placed.count < limit {
      guard let caption = captions[island.regionID], !caption.isEmpty else { continue }
      // Upper case at 9pt with tracking, plus room for the hover glyph.
      let width = min(268, max(64, CGFloat(caption.count) * 6.6 + 30))

      // Clamped to the part of the island that is actually on screen, so an
      // island the camera has zoomed inside of — its true centre far off the
      // canvas — still gets named somewhere the user is looking.
      let reachable = island.bounds.intersection(visible)
      let outside = CGPoint(
        x: min(max(island.center.x, reachable.minX), reachable.maxX),
        y: min(max(island.center.y, reachable.minY), reachable.maxY))
      let lift = min(island.bounds.height / 2 + 14, reachable.height / 2 + 14)

      // On the island first, and as near its middle as there is room for.
      //
      // A name sitting on the ground it names needs nothing else to connect the
      // two. Floated above the coast it becomes one more label among the entity
      // labels — the reader has to work out which shape below it, if any, it
      // belongs to, and on a crowded map the honest answer was often the wrong
      // island. Outside is kept only as the fallback for territories too narrow
      // to hold their own name.
      let inland = interior(of: island, within: reachable, width: width)
      let candidates =
        inland + [
          CGPoint(x: outside.x, y: outside.y - lift),
          CGPoint(x: outside.x, y: outside.y + lift),
        ]

      let boxes = candidates.map {
        CGRect(x: $0.x - width / 2, y: $0.y - 9, width: width, height: 18)
      }
      let fitted = boxes.first { candidate in
        visible.contains(candidate)
          && !occupied.contains(where: { $0.intersects(candidate.insetBy(dx: -8, dy: -7)) })
      }
      // Last resort when the caller insists: the middle of whatever part of the
      // island is on screen, shoved inside the canvas. It may sit on an entity
      // name, which is the lesser of the two wrongs — a territory with no name
      // at all is the one the user reported.
      let rescued =
        insisting
        ? CGRect(
          x: min(max(outside.x - width / 2, 4), max(size.width - width - 4, 4)),
          y: min(max(outside.y - 9, 4), max(size.height - 22, 4)),
          width: width, height: 18)
        : nil
      guard let rect = fitted ?? rescued else { continue }

      occupied.append(rect)
      placed.append(
        Placed(
          regionID: island.regionID, index: island.index, caption: caption, rect: rect,
          ring: island.ring))
    }
    return placed
  }
}
