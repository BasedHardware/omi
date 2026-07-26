import CoreGraphics
import Foundation
import simd

/// Where an entity sits on the atlas should mean something.
///
/// The atlas used to place every node with `f(type, salienceRank, hash(id))`.
/// The edge list was never read, so the one thing the picture could not show
/// was which entities belong together — and worse, type petals actively pulled
/// related entities apart. A meeting and its five attendees are the most
/// related cluster on the map and were guaranteed to land in different petals,
/// rendering the strongest relationship in the graph as five long lines
/// crossing the canvas.
///
/// This layout inverts the rule: relatedness decides position, type only tints
/// and nudges. Neighbourhoods assemble themselves, which is the only way a
/// pattern the user did not already know can appear.
///
/// Everything here is a pure function of its input. Swift seeds string hashing
/// per process, so dictionary iteration order is *not* stable across launches —
/// every traversal that can affect a coordinate walks a sorted array instead,
/// or the same map would lay out differently on every start.
enum MemoryAtlasForceLayout {

  // MARK: - Inputs

  /// One relationship the layout should honour, whichever signal produced it.
  /// Undirected: the layout does not care who was named first.
  struct Link: Equatable {
    let a: String
    let b: String
    let weight: Double

    init(a: String, b: String, weight: Double) {
      // Canonical endpoint order makes merging and equality trivial, and keeps
      // "A relates to B" from being a different link than "B relates to A".
      if a <= b {
        self.a = a
        self.b = b
      } else {
        self.a = b
        self.b = a
      }
      self.weight = weight
    }

    var key: String { "\(a)\u{1}\(b)" }
  }

  /// How a node was placed, so the caller can render it honestly. An entity
  /// with no relationships has not been positioned by relatedness and should
  /// not sit in the middle of the map implying that it was.
  enum Role: Equatable {
    /// Relaxed by the simulation.
    case core
    /// One relationship only: pinned beside the entity it belongs to.
    case leaf(parentID: String)
    /// No relationships at all: parked in the outer halo.
    case isolate
  }

  struct Result {
    /// Normalized canvas coordinates, 0...1 on both axes.
    let positions: [String: CGPoint]
    let roles: [String: Role]
    /// Which neighbourhood each entity was placed in, by opaque group number.
    ///
    /// The layout already has to find these to draw them apart; returning them
    /// is what lets the map say *where* you are rather than only arranging the
    /// dots so that a where exists. Entities with no relationships are absent:
    /// they belong to no neighbourhood, and inventing one for them would be
    /// the same lie the halo exists to avoid.
    let communities: [String: Int]

    init(
      positions: [String: CGPoint],
      roles: [String: Role],
      communities: [String: Int] = [:]
    ) {
      self.positions = positions
      self.roles = roles
      self.communities = communities
    }
  }

  // MARK: - Tunables

  /// The relaxation runs a fixed number of steps because the cooling schedule
  /// *is* the termination condition: displacement each step is capped at the
  /// current temperature, so total movement tracks the schedule down instead of
  /// falling below it. A convergence test was tried and removed — it never
  /// fired, not even on a six-node ring.
  ///
  /// 90 steps is where quality stops paying for itself. Measured on a
  /// 1,096-entity graph with planted communities and a realistic account
  /// holder, the share of a node's ten nearest on-screen neighbours that
  /// genuinely belong to its community runs 0.746 at 60 steps, 0.773 at 90, and
  /// 0.774 at 240 — against 0.023 for chance. Nearly three times the work buys
  /// one thousandth, and this runs inside a SwiftUI `init`.
  static let steps = 90

  /// The type field is deliberately an order of magnitude weaker than the
  /// relationship springs. It keeps the composition orientable — a people-ish
  /// region, a concepts-ish region — without ever overruling the structure. A
  /// person who only appears in one project must be free to drift into that
  /// project's neighbourhood.
  static let typeFieldStrength = 0.022

  /// Pulls disconnected components back toward the middle. Without it they
  /// repel each other to infinity and the fit collapses the interesting part
  /// of the map into a dot.
  static let centerGravity = 0.03

  /// Barnes–Hut opening angle. Layout is an aesthetic computation, not a
  /// physics result, so this runs looser than a simulation would.
  static let theta = 0.9

  /// How far the shorter axis may be stretched to fill the canvas. Enough to
  /// stop a flat graph wasting half the viewport; far short of the point where
  /// a neighbourhood reads as the wrong shape.
  static let maximumAspectStretch = 1.6

  /// A memory naming more entities than this is extraction noise (a calendar
  /// invite with a wall of addresses), and it would contribute k² pairs of
  /// spurious relatedness. Skipped rather than downweighted.
  static let maximumEntitiesPerMemory = 20

  /// Co-occurrence is dense by nature. Keeping only each entity's strongest
  /// few partners is what turns it from a hairball into structure.
  static let coOccurrenceNeighborsPerNode = 6

  /// How much a shared memory is discounted for being shared with something
  /// that is in everything anyway.
  ///
  /// The account holder is not the only superhub. An account has a handful of
  /// entities — the project, the tool, the repository — present in hundreds of
  /// memories, and co-occurring with one of those is true of nearly everything
  /// and separates nothing, which is the same argument that excludes the account
  /// holder from this projection. Left alone they win a slot in almost every
  /// entity's strongest six, so the sparsification that is supposed to expose
  /// structure spends most of its budget re-drawing the same few hubs.
  ///
  /// An exponent on standard inverse document frequency rather than a switch:
  /// 0 is no discount at all, 1 is textbook IDF.
  ///
  /// The largest single improvement any of these constants makes, measured over
  /// six seeds of three fixtures — an even one, one with a few large
  /// cross-linked groups, and one that adds five entities present in a third of
  /// all memories. Without it, on that third fixture those five entities take
  /// **half of every edge the map draws** and community precision collapses to
  /// 0.435; with it they take 19% and precision is 0.866. The other two fixtures
  /// have no such entity by construction and still improve, because the same
  /// discount separates a merely popular entity from a genuinely related one.
  ///
  /// Share of entities drawn inside a neighbourhood that belong to a different
  /// one, without → with: 0.426 → 0.316 even, 0.534 → 0.438 large-cluster,
  /// 0.868 → 0.608 superhub. It also tightens how far the map's outliers reach
  /// (2.126 → 2.017 on the large-cluster fixture), which is what pays back the
  /// spread that `communitySeparation` costs.
  static let coOccurrenceSpecificity = 1.0

  /// What is left of a relationship to the account holder once it is no longer
  /// allowed to decide the map.
  ///
  /// Excluding them from co-occurrence removes the meaningless half of their
  /// pull, but the edges the extractor actually drew are real assertions, and
  /// at full strength a few hundred of them still aim at one pinned point and
  /// collapse the map onto it. Damped, they act as a tether: an entity related
  /// to nothing but you still hangs near the middle instead of being flung to
  /// the rim, and everything else is free to group by what it is *actually*
  /// related to.
  ///
  /// Not zero, and measured rather than guessed: on a planted-community graph
  /// with a realistic ego, community precision peaks around here (0.756) and
  /// falls off on both sides — 0.717 at full strength, 0.751 with no tether at
  /// all.
  static let anchorTetherStrength = 0.1

  /// How much room the account holder keeps around themselves, as a multiple of
  /// the repulsion an ordinary entity carries.
  ///
  /// They are pinned at the centre and nearly everything retains some tether to
  /// them, so the middle of the map is where the crowd is pressed hardest and
  /// least readable — the one place a person looks first. As a plain node they
  /// push back with a single entity's worth of repulsion against several hundred
  /// entities' worth of pull.
  ///
  /// Weighting only their repulsion, and leaving `anchorTetherStrength` alone,
  /// keeps the two halves of the account holder's treatment separable: the
  /// tether still says who is related to them, this only says how close anyone
  /// needs to stand to make that point.
  ///
  /// Measured as the gap between the account holder and the twenty entities
  /// nearest them, in units of the typical gap between neighbours anywhere on
  /// the map: 5.76 without this and 6.85 with it on the account-shaped fixture.
  ///
  /// The only constant here that is not free, and the trade is deliberate. It
  /// costs about 0.01 of community precision (0.765 → 0.755 even, 0.922 → 0.908
  /// large-cluster) and about 0.01 of neighbourhood distinctness, and it buys
  /// the one thing those measures cannot see: whether a person can read the
  /// middle of their own map. Keep the cost in view if it ever grows — what
  /// justifies it is the clearing, not the aggregates.
  ///
  /// A share of the map rather than a fixed weight, because the crowd being
  /// held off *is* the map and its size varies by three orders of magnitude
  /// between accounts. A thousand-entity account comes to roughly forty
  /// entities' worth of push; a twenty-six entity one comes to none, which is
  /// correct — it has no crowding to fix. Fixed at forty instead, that small
  /// map is blown apart hard enough to collide its own labels, which is how
  /// this came to be a share.
  static let anchorRepulsionShare = 0.04

  /// How hard a detected neighbourhood pulls itself together, against the
  /// spreading the rest of the simulation does.
  ///
  /// Measured on the account-shaped fixture, as the mean distance within a
  /// neighbourhood over the mean distance across the whole map: 0.266 with no
  /// cohesion, 0.234 here, 0.202 at twice this. Community precision peaks here
  /// too — 0.756 / 0.773 / 0.762 across those three — so tighter groups past
  /// this point are bought by putting the wrong entities in them.
  static let communityCohesion = 1.0

  /// How hard two neighbourhoods push each other apart when they overlap.
  ///
  /// Cohesion alone cannot separate anything: it holds each group to its own
  /// radius, and two groups satisfy that perfectly while sitting on top of one
  /// another. Everything keeping them apart was the same repulsion every
  /// individual entity feels, which knows nothing about groups — so several
  /// heavily interlinked neighbourhoods land in one place and read as a single
  /// mess, exactly where the map is busiest and legibility matters most.
  ///
  /// Deliberately a resolution of *overlap* rather than a force at all
  /// distances. Groups already well apart feel nothing, so the parts of the map
  /// that were legible stay where they are and the correction is spent only
  /// where two groups are genuinely claiming the same space.
  ///
  /// Measured as the share of entities sitting inside a neighbourhood's drawn
  /// disc that belong to a *different* neighbourhood, over six seeds of two
  /// fixtures — the even one, and one shaped like the case this exists for,
  /// three large heavily cross-linked groups amid a long tail of small ones:
  ///
  /// - even: 0.376 without separation, 0.316 with
  /// - large-cluster: 0.501 without, 0.438 with
  /// - superhub: 0.666 without, 0.608 with
  ///
  /// Community precision does not pay for it (0.750 → 0.755 and 0.901 → 0.908),
  /// which is what should happen: this moves whole groups, so it cannot change
  /// which entities are near each other inside one.
  ///
  /// Held well below the point where the metric peaks, and deliberately. Pushed
  /// harder the groups do read as more distinct, but the map pays for it in a
  /// way no per-group measure catches: the bulk of the entities bunch toward the
  /// middle while the sparse tail is fitted to the canvas edge, and the result
  /// is a dense blob ringed by scattered specks. That shows up as the ratio of
  /// the 95th-percentile radius to the median, which at 1.0 here reached 2.6 on
  /// the large-cluster fixture against 2.0 left alone; at this strength it is
  /// 2.1, and on the even fixture it is unchanged at 1.95.
  static let communitySeparation = 0.4

  /// How far past the drawing area the unconnected entities ring the map, as a
  /// fraction of its half-extent.
  ///
  /// Enough to read as "outside", and no more. This used to be 0.07 with a
  /// further 0.05 per ring on top, which put a lone entity most of a
  /// canvas-width from anything it could be compared to — the map looked like
  /// it had shed debris. The floor is the drawing area itself and cannot go
  /// lower: everything the relaxation placed is fitted inside it, so coming any
  /// closer would put an entity with no relationships among entities whose
  /// positions mean something.
  static let haloClearance = 0.05

  /// What share of the map the fit is required to fit.
  ///
  /// Not all of it, and now not almost all of it either. The relaxation leaves a
  /// thin tail of loosely attached stragglers a long way out, and scaling so
  /// that *they* land on the edge squeezes everything worth reading into the
  /// middle — which is the same defect twice over: the structure looks like a
  /// clump, and the ring of unconnected entities outside the drawing area then
  /// sits an absurd distance from it.
  ///
  /// The tail is not discarded; it is drawn past the area, which the canvas has
  /// room for. Measured on the account-shaped fixtures as the share of entities
  /// inside the drawing area, this moves the bulk outward without pushing more
  /// than a few percent of the map past the edge.
  static let fittedShare = 0.90

  /// The smallest group the separation force will move.
  ///
  /// Deliberately the same six the UI uses to decide a group is worth naming
  /// (`MemoryAtlasLayoutEngine.neighbourhoods`), because the two answer the same
  /// question: is this a place on the map, or a few entities that happen to be
  /// adjacent? Pushing apart groups the map will never name spends the canvas on
  /// distinctions the user is never shown.
  static let namedGroupFloor = 6.0

  /// The background left between two neighbourhoods once their edges clear, as
  /// a multiple of the *smaller* one's extent.
  ///
  /// A gap rather than merely touching: a row of tangent discs still reads as
  /// one continuous field, and the map only separates into places when there is
  /// space between them.
  ///
  /// Scaled by the smaller of the two, which is what keeps the rim clean. Scaled
  /// by the pair's combined size instead, every small group in the account is
  /// required to clear the largest group's whole radius with half as much again
  /// on top — a distance that has nothing to do with the small group and puts it
  /// off the edge of the map. Since the push is split by population the small
  /// group does all of that moving, so dozens of them end up flung into a ring
  /// of debris around a centre that never opened up.
  ///
  /// It also gives "bigger clusters separate more" for free: two large
  /// neighbourhoods clear each other's full extent *and* take the wide margin,
  /// while a handful of entities beside a large group takes a narrow one.
  static let communityClearance = 0.6

  // MARK: - Deriving relatedness

  /// Relationships the extractor actually drew.
  ///
  /// Weight comes from how many memories assert the relationship: two entities
  /// linked from eleven separate memories are more related than two linked
  /// once. Deliberately not the number of distinct verbs between them — the
  /// server mints a separate edge per verb, so counting verbs would score
  /// "includes" plus "with" as twice the relationship they jointly describe.
  static func explicitLinks(
    edges: [(sourceID: String, targetID: String, memoryCount: Int)]
  ) -> [Link] {
    merge(
      edges.compactMap { edge in
        guard edge.sourceID != edge.targetID else { return nil }
        return Link(
          a: edge.sourceID,
          b: edge.targetID,
          weight: 1 + log1p(Double(max(edge.memoryCount, 0)))
        )
      })
  }

  /// Relationships nobody drew.
  ///
  /// Every node carries the ids of the memories it was extracted from, which
  /// means the client already holds a complete entity↔memory incidence
  /// structure and has only ever used it to populate the evidence list.
  /// Projecting it gives relatedness the edge list does not contain: two people
  /// who appear in eleven of the same memories are related whether or not the
  /// extractor happened to emit a verb between them.
  ///
  /// Each shared memory contributes `1 / (k - 1)`, the standard collaboration
  /// weighting — otherwise one eight-person meeting would assert eight strong
  /// friendships, and group events would dominate the whole map.
  ///
  /// - Parameter anchorID: the account holder, excluded from the projection.
  ///   They are a participant in nearly every memory by construction, so
  ///   "co-occurs with you" is true of almost everything and distinguishes
  ///   nothing — it is the one relationship in the graph that carries no
  ///   information. Left in, it does double damage: it makes the account
  ///   holder every entity's strongest partner, and it inflates `k` for every
  ///   memory, so the relationships that *are* informative each get a smaller
  ///   share of it.
  static func coOccurrenceLinks(
    memoryIDsByNodeID: [String: [String]],
    excluding anchorID: String?
  ) -> [Link] {
    var nodeIDsByMemoryID: [String: [String]] = [:]
    for nodeID in memoryIDsByNodeID.keys.sorted() where nodeID != anchorID {
      for memoryID in memoryIDsByNodeID[nodeID] ?? [] {
        nodeIDsByMemoryID[memoryID, default: []].append(nodeID)
      }
    }

    // How much one shared memory is worth as evidence, per entity. Standard
    // inverse document frequency: an entity present in half your memories tells
    // you almost nothing by being present in one more.
    //
    // Smoothed with `1 +` so an entity in *every* memory is heavily discounted
    // rather than annihilated — it is still a real thing that was really there,
    // and zeroing it would delete relationships rather than rank them.
    var evidence: [String: Double] = [:]
    let totalMemories = max(Double(nodeIDsByMemoryID.count), 1)
    for nodeID in memoryIDsByNodeID.keys.sorted() where nodeID != anchorID {
      let appearances = Double(Set(memoryIDsByNodeID[nodeID] ?? []).count)
      guard appearances > 0 else { continue }
      evidence[nodeID] = pow(log(1 + totalMemories / appearances), coOccurrenceSpecificity)
    }

    var weights: [String: Double] = [:]
    var endpoints: [String: (String, String)] = [:]
    for memoryID in nodeIDsByMemoryID.keys.sorted() {
      // Deduplicated: an entity can cite the same memory twice — most easily
      // when a self-node is folded into the anchor and brings its memories
      // with it. Counting it twice both mis-scales the 1/(k-1) share and can
      // push a legitimate memory past the noise cap, which would silently
      // discard every relationship it implies.
      let participants = Set(nodeIDsByMemoryID[memoryID] ?? []).sorted()
      guard participants.count >= 2, participants.count <= maximumEntitiesPerMemory else { continue }
      let share = 1 / Double(participants.count - 1)
      for i in 0..<participants.count {
        for j in (i + 1)..<participants.count {
          // Both ends count: a memory shared by two specific entities is strong
          // evidence, one shared by a specific entity and a ubiquitous one is
          // mostly a statement about the ubiquitous one.
          let specific =
            share * (evidence[participants[i]] ?? 1)
            * (evidence[participants[j]] ?? 1)
          let link = Link(a: participants[i], b: participants[j], weight: specific)
          weights[link.key, default: 0] += specific
          endpoints[link.key] = (link.a, link.b)
        }
      }
    }

    let all = weights.keys.sorted().compactMap { key -> Link? in
      guard let pair = endpoints[key], let weight = weights[key] else { return nil }
      return Link(a: pair.0, b: pair.1, weight: weight)
    }
    return strongestPerNode(all, limit: coOccurrenceNeighborsPerNode)
  }

  /// Sparsifies a dense weighted link set to each node's strongest partners.
  /// A link survives if *either* endpoint counts it among its best, so a
  /// popular hub cannot orphan a small entity whose only real relationship is
  /// with that hub.
  static func strongestPerNode(_ links: [Link], limit: Int) -> [Link] {
    guard limit > 0 else { return [] }
    var byNode: [String: [Link]] = [:]
    for link in links {
      byNode[link.a, default: []].append(link)
      byNode[link.b, default: []].append(link)
    }

    var keptKeys: Set<String> = []
    for nodeID in byNode.keys.sorted() {
      let ranked = (byNode[nodeID] ?? []).sorted {
        $0.weight == $1.weight ? $0.key < $1.key : $0.weight > $1.weight
      }
      for link in ranked.prefix(limit) { keptKeys.insert(link.key) }
    }
    return links.filter { keptKeys.contains($0.key) }
  }

  /// Loosens every relationship that touches the account holder.
  ///
  /// Applied inside `layout` rather than at the call site, so the rule holds
  /// for whatever mix of signals a caller merges: nothing that touches the
  /// anchor gets to decide where the rest of the map goes. See
  /// `anchorTetherStrength` for why the answer is "loosened", not "removed".
  static func tetherToAnchor(_ links: [Link], anchorID: String?) -> [Link] {
    guard let anchorID else { return links }
    return links.map { link in
      guard link.a == anchorID || link.b == anchorID else { return link }
      return Link(a: link.a, b: link.b, weight: link.weight * anchorTetherStrength)
    }
  }

  /// Sums duplicate pairs into one link. Callers combine signals by simply
  /// concatenating link sets and merging.
  static func merge(_ links: [Link]) -> [Link] {
    var weights: [String: Double] = [:]
    var order: [String] = []
    var endpoints: [String: (String, String)] = [:]
    for link in links where link.a != link.b {
      if weights[link.key] == nil {
        order.append(link.key)
        endpoints[link.key] = (link.a, link.b)
      }
      weights[link.key, default: 0] += link.weight
    }
    return order.compactMap { key in
      guard let pair = endpoints[key], let weight = weights[key] else { return nil }
      return Link(a: pair.0, b: pair.1, weight: weight)
    }
  }

  // MARK: - Layout

  /// - Parameters:
  ///   - nodeIDs: every node to place. Order is irrelevant; the layout sorts.
  ///   - links: relatedness, already merged across signals.
  ///   - anchorID: the account holder, pinned at the centre of the canvas.
  ///   - typeTargets: the weak per-node field target, in normalized canvas
  ///     coordinates. Nodes without one feel no type pull.
  ///   - area: the normalized region the relaxed map may occupy. Isolates are
  ///     parked in the margin outside it.
  static func layout(
    nodeIDs: [String],
    links: [Link],
    anchorID: String?,
    typeTargets: [String: CGPoint],
    area: CGRect,
    steps: Int = MemoryAtlasForceLayout.steps
  ) -> Result {
    let identifiers = nodeIDs.sorted()
    guard !identifiers.isEmpty else { return Result(positions: [:], roles: [:]) }

    let known = Set(identifiers)
    // Sorted, not merely merged. Spring forces are summed in this order, and
    // floating-point addition is not associative, so leaving the server's
    // encounter order in place would let the same graph delivered in a
    // different order drift into a visibly different map over 90 steps.
    //
    // Damping happens here rather than at the call site so the rule holds for
    // whatever mix of signals a caller merges: nothing that touches the anchor
    // gets to decide the map.
    let merged = tetherToAnchor(
      merge(links.filter { known.contains($0.a) && known.contains($0.b) }), anchorID: anchorID
    ).sorted { $0.key < $1.key }

    var neighbors: [String: [(id: String, weight: Double)]] = [:]
    for link in merged {
      neighbors[link.a, default: []].append((link.b, link.weight))
      neighbors[link.b, default: []].append((link.a, link.weight))
    }
    for key in neighbors.keys {
      neighbors[key]?.sort { $0.weight == $1.weight ? $0.id < $1.id : $0.weight > $1.weight }
    }

    // Small islands are kept out of the relaxation entirely.
    //
    // A real account carries dozens of two- and three-entity fragments with no
    // path to anything else. Relaxed alongside the main graph they are simply
    // repelled outward until they ring the canvas, and because they then define
    // its extent, the structure worth looking at gets fitted into a fifth of
    // the width. They belong with the isolates, at the edge.
    let islands = outlyingIslands(
      identifiers: identifiers, neighbors: neighbors, anchorID: anchorID)
    let roles = classify(
      identifiers: identifiers, neighbors: neighbors, anchorID: anchorID, outlying: islands.parked)
    let coreIDs = identifiers.filter { roles[$0] == .core }

    guard !coreIDs.isEmpty else {
      // Nothing is related to anything. There is no structure to draw, so every
      // node goes to the halo rather than to a fake constellation. An anchor
      // that exists is always core, so reaching here means there is no anchor.
      return Result(
        positions: haloPositions(groups: identifiers.map { [$0] }, area: area), roles: roles)
    }

    var indexOf: [String: Int] = [:]
    for (index, id) in coreIDs.enumerated() { indexOf[id] = index }

    let springs: [(i: Int, j: Int, weight: Double)] = merged.compactMap { link in
      guard let i = indexOf[link.a], let j = indexOf[link.b] else { return nil }
      return (i, j, link.weight)
    }
    let normalizedSprings = normalizeSpringWeights(springs)

    var points = radialInitialPositions(
      coreIDs: coreIDs, indexOf: indexOf, neighbors: neighbors, anchorID: anchorID)
    let pinnedIndex = anchorID.flatMap { indexOf[$0] }
    if let pinnedIndex { points[pinnedIndex] = .zero }

    // The weak type field, resolved into the same working space the simulation
    // uses. Canvas coordinates run 0...1 with y downward; the simulation works
    // in a centred [-1, 1] box, so targets are mapped once up front.
    let fieldTargets: [SIMD2<Double>?] = coreIDs.map { id in
      guard let target = typeTargets[id] else { return nil }
      return SIMD2<Double>((Double(target.x) - 0.5) * 2, (Double(target.y) - 0.5) * 2)
    }

    // Neighbourhoods, and the force that makes them visible. Relaxation alone
    // recovers structure but spreads it evenly, because that is what
    // Fruchterman–Reingold optimises for: a graph whose groups are perfectly
    // recoverable still draws as an even haze. Naming the groups and letting
    // each one pull itself together is what turns recoverable structure into
    // structure you can see without being told where to look.
    //
    // The anchor is excluded: pinned at the centre and belonging to whichever
    // group its remaining tether happens to favour, it would drag that one
    // group onto the middle of the map.
    let communityOf = detectCommunities(coreIDs: coreIDs, neighbors: neighbors)
    let communities = coreIDs.enumerated().map { index, id in
      index == pinnedIndex ? -1 : (communityOf[id] ?? -1)
    }

    relax(
      points: &points,
      springs: normalizedSprings,
      fieldTargets: fieldTargets,
      communities: communities,
      communityCount: (communities.max() ?? -1) + 1,
      pinnedIndex: pinnedIndex,
      steps: steps)

    orientCanonically(&points, coreIDs: coreIDs, neighbors: neighbors, pinnedIndex: pinnedIndex)

    var positions = fit(
      points: points, coreIDs: coreIDs, pinnedIndex: pinnedIndex, area: area)
    separateCrowdedMarks(&positions, coreIDs: coreIDs, anchorID: anchorID, area: area)
    placeLeaves(into: &positions, identifiers: identifiers, roles: roles, area: area)

    // Islands first and kept together, so a three-entity fragment reads as one
    // small group on the rim rather than three unrelated specks; then the
    // genuinely unconnected, in a stable order.
    var groups = islands.groups.map { $0.filter { roles[$0] == .isolate } }.filter { !$0.isEmpty }
    groups += identifiers.filter { roles[$0] == .isolate && !islands.parked.contains($0) }.map { [$0] }
    for (id, point) in haloPositions(groups: groups, area: area) { positions[id] = point }

    // A leaf was never relaxed — it is pinned beside its parent — so it has no
    // community of its own. It reads as part of whatever its parent belongs to,
    // which is also the only honest thing to say about an entity whose single
    // relationship is to that parent.
    // The anchor is excluded here for the same reason it is excluded from the
    // cohesion force, and for one more: a neighbourhood is described by its
    // strongest members, and the account holder outranks everyone everywhere.
    // Let them join a group and every group is named after them.
    var membership = communityOf
    if let anchorID { membership[anchorID] = nil }
    for id in identifiers {
      if case .leaf(let parentID) = roles[id], let group = membership[parentID] {
        membership[id] = group
      }
    }

    return Result(positions: positions, roles: roles, communities: membership)
  }

  // MARK: - Classification

  /// A leaf's only spatial information is who its parent is. Spending a
  /// simulation slot on it produces fog; pinning it beside its parent produces
  /// a burr on a hub, which is both truer and cheaper.
  ///
  /// A degree-1 node whose only neighbour is *also* degree-1 stays core: the
  /// pair is a two-node component, and hanging one off the other would leave
  /// nothing to hang it from.
  static func classify(
    identifiers: [String],
    neighbors: [String: [(id: String, weight: Double)]],
    anchorID: String?,
    outlying: Set<String> = []
  ) -> [String: Role] {
    var roles: [String: Role] = [:]
    for id in identifiers {
      let adjacent = neighbors[id] ?? []
      if id == anchorID {
        roles[id] = .core
      } else if adjacent.isEmpty || outlying.contains(id) {
        roles[id] = .isolate
      } else if adjacent.count == 1, (neighbors[adjacent[0].id] ?? []).count > 1,
        !outlying.contains(adjacent[0].id)
      {
        roles[id] = .leaf(parentID: adjacent[0].id)
      } else {
        roles[id] = .core
      }
    }
    return roles
  }

  /// An island small enough that relaxing it alongside the main graph costs
  /// more than it is worth. Returns the members to park, ordered so that an
  /// island's own entities stay adjacent when they reach the halo.
  static func outlyingIslands(
    identifiers: [String],
    neighbors: [String: [(id: String, weight: Double)]],
    anchorID: String?,
    minimumRelaxedSize: Int = 6
  ) -> (parked: Set<String>, groups: [[String]]) {
    var componentOf: [String: Int] = [:]
    var components: [[String]] = []

    for id in identifiers where componentOf[id] == nil {
      var members: [String] = []
      var stack = [id]
      componentOf[id] = components.count
      while let current = stack.popLast() {
        members.append(current)
        for neighbor in neighbors[current] ?? [] where componentOf[neighbor.id] == nil {
          componentOf[neighbor.id] = components.count
          stack.append(neighbor.id)
        }
      }
      components.append(members.sorted())
    }

    // The account holder's own island is the map, whatever its size. Failing
    // an anchor, the biggest island is.
    let mainIndex =
      anchorID.flatMap { componentOf[$0] }
      ?? components.indices.max { components[$0].count < components[$1].count }

    var parked: Set<String> = []
    var groups: [[String]] = []
    let outlying = components.indices
      .filter { $0 != mainIndex && components[$0].count < minimumRelaxedSize }
      .sorted {
        components[$0].count == components[$1].count
          ? components[$0][0] < components[$1][0]
          : components[$0].count > components[$1].count
      }
    for index in outlying {
      // Single entities already read as unconnected; leave them to the plain
      // isolate ordering rather than claiming they form an island.
      guard components[index].count > 1 else { continue }
      parked.formUnion(components[index])
      groups.append(components[index])
    }
    return (parked, groups)
  }

  // MARK: - Initial positions

  /// Breadth-first from the anchor: hop distance becomes radius, and each
  /// node's angular slice is subdivided among its children.
  ///
  /// This matters more than it looks. An ego graph laid out radially is already
  /// approximately right, so relaxation refines a sane picture instead of
  /// untangling a random cloud — which is what lets the step budget be small
  /// enough to run synchronously.
  static func radialInitialPositions(
    coreIDs: [String],
    indexOf: [String: Int],
    neighbors: [String: [(id: String, weight: Double)]],
    anchorID: String?
  ) -> [SIMD2<Double>] {
    var points = [SIMD2<Double>](repeating: .zero, count: coreIDs.count)
    var placed = [Bool](repeating: false, count: coreIDs.count)

    // Components are seeded around a ring so they start apart rather than
    // stacked on the origin, where repulsion would have to shove them past
    // each other before any real structure could form.
    var roots: [String] = []
    if let anchorID, indexOf[anchorID] != nil { roots.append(anchorID) }
    var componentIndex = 0

    func sweep(from root: String, arcStart: Double, arcWidth: Double, origin: SIMD2<Double>) {
      guard let rootIndex = indexOf[root], !placed[rootIndex] else { return }
      points[rootIndex] = origin
      placed[rootIndex] = true

      var frontier: [(id: String, arcStart: Double, arcWidth: Double)] = [
        (root, arcStart, arcWidth)
      ]
      var hop = 1
      while !frontier.isEmpty && hop < 24 {
        var next: [(id: String, arcStart: Double, arcWidth: Double)] = []
        let radius = 0.28 * Double(hop)
        for parent in frontier {
          let children = (neighbors[parent.id] ?? []).filter { child in
            guard let index = indexOf[child.id] else { return false }
            return !placed[index]
          }
          guard !children.isEmpty else { continue }
          let slice = parent.arcWidth / Double(children.count)
          for (offset, child) in children.enumerated() {
            guard let index = indexOf[child.id] else { continue }
            placed[index] = true
            let angle = parent.arcStart + slice * (Double(offset) + 0.5)
            points[index] = origin + SIMD2<Double>(cos(angle) * radius, sin(angle) * radius)
            next.append((child.id, parent.arcStart + slice * Double(offset), slice))
          }
        }
        frontier = next
        hop += 1
      }
    }

    // Remaining components, largest first, so the biggest structure gets the
    // most central seed.
    let unseeded = coreIDs.filter { $0 != anchorID }
      .sorted {
        let lhs = (neighbors[$0] ?? []).count
        let rhs = (neighbors[$1] ?? []).count
        return lhs == rhs ? $0 < $1 : lhs > rhs
      }
    roots.append(contentsOf: unseeded)

    for root in roots {
      guard let index = indexOf[root], !placed[index] else { continue }
      let origin: SIMD2<Double>
      if root == anchorID {
        origin = .zero
      } else {
        let angle = Double(componentIndex) * 2.399_963_229_728_653
        let radius = 0.35 + 0.06 * Double(componentIndex)
        origin = SIMD2<Double>(cos(angle) * radius, sin(angle) * radius)
        componentIndex += 1
      }
      sweep(from: root, arcStart: 0, arcWidth: 2 * .pi, origin: origin)
    }
    return points
  }

  // MARK: - Communities

  /// Groups the graph into neighbourhoods, by modularity (Louvain).
  ///
  /// Modularity asks whether a group has more internal relationships than it
  /// would by chance given its members' degrees, which is the right question
  /// here: without the degree term, "everyone who ever appeared with Omi" wins
  /// every time, because the popular entities are popular everywhere.
  ///
  /// Label propagation was tried first and is a third of the code, but it
  /// collapses on this shape of graph — on a thousand-entity account-shaped
  /// fixture it merged 558 of 810 entities into one label, and the pairs it
  /// grouped were related no more often than chance. Modularity resists that
  /// by construction: absorbing an unrelated entity costs more than it pays.
  ///
  /// Determinism is the whole game, because these groups move nodes. Nodes are
  /// visited in `coreIDs` order (the caller sorts), candidate groups in index
  /// order, and a tie leaves a node where it is.
  static func detectCommunities(
    coreIDs: [String],
    neighbors: [String: [(id: String, weight: Double)]],
    levels: Int = 10
  ) -> [String: Int] {
    guard !coreIDs.isEmpty else { return [:] }
    var indexOf: [String: Int] = [:]
    for (index, id) in coreIDs.enumerated() { indexOf[id] = index }

    var adjacency: [[(node: Int, weight: Double)]] = Array(repeating: [], count: coreIDs.count)
    for (index, id) in coreIDs.enumerated() {
      for neighbor in neighbors[id] ?? [] {
        guard let other = indexOf[neighbor.id], other != index else { continue }
        adjacency[index].append((other, neighbor.weight))
      }
    }
    var selfLoops = [Double](repeating: 0, count: coreIDs.count)

    // Which group each original node currently belongs to, followed down
    // through however many levels of aggregation the graph supports.
    var membership = Array(0..<coreIDs.count)
    for _ in 0..<levels {
      let (partition, groups) = mergeByModularity(adjacency: adjacency, selfLoops: selfLoops)
      guard groups < adjacency.count else { break }
      membership = membership.map { partition[$0] }
      (adjacency, selfLoops) = collapse(
        adjacency: adjacency, selfLoops: selfLoops, into: partition, groups: groups)
    }

    var result: [String: Int] = [:]
    for (index, id) in coreIDs.enumerated() { result[id] = membership[index] }
    return result
  }

  /// One Louvain level: move each node to whichever neighbouring group its
  /// membership improves most, until nothing improves.
  ///
  /// The gain from moving node `i` into group `C` is `w(i, C) - Σtot(C)·k(i)/2m`
  /// — what `i` actually shares with `C`, less what a graph with the same
  /// degrees would have produced by accident.
  private static func mergeByModularity(
    adjacency: [[(node: Int, weight: Double)]],
    selfLoops: [Double],
    rounds: Int = 20
  ) -> (partition: [Int], groups: Int) {
    let count = adjacency.count
    var degree = [Double](repeating: 0, count: count)
    for index in 0..<count {
      degree[index] = adjacency[index].reduce(0) { $0 + $1.weight } + 2 * selfLoops[index]
    }
    let twiceTotal = degree.reduce(0, +)
    guard twiceTotal > 0 else { return (Array(0..<count), count) }

    var group = Array(0..<count)
    var groupDegree = degree
    for _ in 0..<rounds {
      var moved = false
      for index in 0..<count {
        let current = group[index]
        groupDegree[current] -= degree[index]

        var shared: [Int: Double] = [:]
        for edge in adjacency[index] { shared[group[edge.node], default: 0] += edge.weight }

        var best = current
        var bestGain = (shared[current] ?? 0) - groupDegree[current] * degree[index] / twiceTotal
        for candidate in shared.keys.sorted() {
          let gain =
            (shared[candidate] ?? 0) - groupDegree[candidate] * degree[index] / twiceTotal
          if gain > bestGain + 1e-12 {
            bestGain = gain
            best = candidate
          }
        }

        groupDegree[best] += degree[index]
        if best != current {
          group[index] = best
          moved = true
        }
      }
      if !moved { break }
    }

    var dense: [Int: Int] = [:]
    var partition = [Int](repeating: 0, count: count)
    for index in 0..<count {
      let label = group[index]
      let renumbered = dense[label] ?? dense.count
      dense[label] = renumbered
      partition[index] = renumbered
    }
    return (partition, dense.count)
  }

  /// Rebuilds the graph with each group as a single node, so the next level can
  /// look for groups *of* groups. Internal weight becomes a self-loop, which is
  /// what carries a group's own density up to the next level.
  private static func collapse(
    adjacency: [[(node: Int, weight: Double)]],
    selfLoops: [Double],
    into partition: [Int],
    groups: Int
  ) -> ([[(node: Int, weight: Double)]], [Double]) {
    var collapsedSelfLoops = [Double](repeating: 0, count: groups)
    var collapsedEdges: [[Int: Double]] = Array(repeating: [:], count: groups)
    for index in 0..<adjacency.count {
      let source = partition[index]
      collapsedSelfLoops[source] += selfLoops[index]
      for edge in adjacency[index] {
        let target = partition[edge.node]
        if source == target {
          // Every undirected relationship appears once from each end.
          collapsedSelfLoops[source] += edge.weight / 2
        } else {
          collapsedEdges[source][target, default: 0] += edge.weight
        }
      }
    }
    let rebuilt = collapsedEdges.map { edges in
      edges.keys.sorted().compactMap { node in
        edges[node].map { (node: node, weight: $0) }
      }
    }
    return (rebuilt, collapsedSelfLoops)
  }

  // MARK: - Relaxation

  /// Compresses the weight range so the strongest relationship pulls harder
  /// than the weakest without collapsing everything else into a point. A raw
  /// weight range of 1...400 would make 99% of the graph behave identically.
  static func normalizeSpringWeights(
    _ springs: [(i: Int, j: Int, weight: Double)]
  ) -> [(i: Int, j: Int, weight: Double)] {
    guard let maximum = springs.map(\.weight).max(), maximum > 0 else { return springs }
    let scale = log1p(maximum)
    return springs.map { spring in
      (spring.i, spring.j, 0.35 + 0.95 * (log1p(max(spring.weight, 0)) / scale))
    }
  }

  /// Fruchterman–Reingold with Barnes–Hut repulsion and a cooling schedule.
  private static func relax(
    points: inout [SIMD2<Double>],
    springs: [(i: Int, j: Int, weight: Double)],
    fieldTargets: [SIMD2<Double>?],
    communities: [Int],
    communityCount: Int,
    pinnedIndex: Int?,
    steps: Int
  ) {
    let count = points.count
    guard count > 1 else { return }

    // Ideal separation for the working box, the standard FR estimate.
    let k = 2.0 / sqrt(Double(count))
    let kSquared = k * k

    // The crowd the account holder is holding off is the map itself, so that is
    // what their push is scaled to. The quadtree already gives them an ordinary
    // node's worth, so this is only the excess on top — which on a map small
    // enough not to have the problem comes out at nothing.
    let anchorExcessRepulsion =
      pinnedIndex == nil ? 0 : max(0, Double(count) * anchorRepulsionShare - 1)
    var displacements = [SIMD2<Double>](repeating: .zero, count: count)
    var traversal: [Int] = []
    traversal.reserveCapacity(64)
    var centroids = [SIMD2<Double>](repeating: .zero, count: max(communityCount, 1))
    var populations = [Double](repeating: 0, count: max(communityCount, 1))
    var radii = [Double](repeating: 0, count: max(communityCount, 1))
    // The room a group *wants* and the room it actually takes up are different
    // numbers, and separation needs the second one. `radii` is the ideal-spacing
    // estimate the containment wall is built from; cohesion then packs the group
    // far tighter than that, so asking two neighbourhoods to clear each other's
    // ideal radius demands more of the canvas than exists and the force spends
    // itself in a stalemate against centre gravity.
    var extents = [Double](repeating: 0, count: max(communityCount, 1))
    // One displacement per group rather than per member: separation has to move
    // a neighbourhood without deforming it, or it would be fighting the very
    // cohesion that made the group worth drawing.
    var groupShifts = [SIMD2<Double>](repeating: .zero, count: max(communityCount, 1))
    // Skipped for a single group: holding one group together is centre gravity
    // by another name, and there is nothing for it to be held apart *from*.
    // Not load-bearing — containment is what keeps a lone group from
    // imploding, and it does that whether or not this shortcut is taken.
    let cohering = communityCohesion > 0 && communityCount > 1

    for step in 0..<steps {
      for i in 0..<count { displacements[i] = .zero }

      let tree = Quadtree(points: points)
      for i in 0..<count where i != pinnedIndex {
        displacements[i] += tree.repulsion(
          on: points[i], kSquared: kSquared, theta: theta, stack: &traversal)
      }

      // The account holder repels as if they were a crowd. The quadtree has
      // already counted them once as an ordinary node, so only the excess is
      // added here, in the same form the tree uses.
      if let pinnedIndex, anchorExcessRepulsion > 0 {
        let anchor = points[pinnedIndex]
        for i in 0..<count where i != pinnedIndex {
          let delta = points[i] - anchor
          let distance = simd_length(delta)
          guard distance > 1e-9 else { continue }
          displacements[i] += (delta / distance) * (kSquared * anchorExcessRepulsion / distance)
        }
      }

      for spring in springs {
        let delta = points[spring.j] - points[spring.i]
        let distance = simd_length(delta)
        guard distance > 1e-9 else { continue }
        let force = (delta / distance) * (spring.weight * distance * distance / k)
        if spring.i != pinnedIndex { displacements[spring.i] += force }
        if spring.j != pinnedIndex { displacements[spring.j] -= force }
      }

      if cohering {
        for index in 0..<centroids.count {
          centroids[index] = .zero
          populations[index] = 0
        }
        for i in 0..<count where communities[i] >= 0 {
          centroids[communities[i]] += points[i]
          populations[communities[i]] += 1
        }
        for index in 0..<centroids.count where populations[index] > 0 {
          centroids[index] /= populations[index]
          // The room a group of this size needs at the simulation's own ideal
          // spacing. Containing a group to its natural radius keeps it together
          // without squeezing it: pulling toward a bare centroid instead would
          // collapse the group to a point, and on a map with few groups it
          // would collapse the whole thing — after which the separation pass
          // re-scatters the wreckage on an even grid and every trace of
          // structure is gone.
          radii[index] = k * sqrt(populations[index] / .pi)
          extents[index] = 0
        }

        // Root-mean-square spread, which for a group spread evenly over a disc
        // is its radius over √2 — so scaling back up recovers the edge of the
        // group as drawn. A mean would understate it and a true maximum would
        // let one strayed member speak for the whole neighbourhood.
        for i in 0..<count where communities[i] >= 0 {
          extents[communities[i]] += simd_length_squared(points[i] - centroids[communities[i]])
        }
        for index in 0..<extents.count where populations[index] > 0 {
          extents[index] = sqrt(2 * extents[index] / populations[index])
        }

        // Only groups big enough for the map to name as a region take part. The
        // force exists to make those regions legible, so a pair of them is the
        // only thing it should be rearranging — and the extent it works from
        // treats a group as a disc, which a handful of entities strung along a
        // chain is not. Applied to those, it reads their length as a radius and
        // shoves far harder than their size warrants, which on a small account
        // is enough to push names into each other.
        for index in 0..<groupShifts.count { groupShifts[index] = .zero }
        for a in 0..<centroids.count where populations[a] >= namedGroupFloor {
          for b in (a + 1)..<centroids.count where populations[b] >= namedGroupFloor {
            let delta = centroids[b] - centroids[a]
            let distance = simd_length(delta)
            let wanted =
              extents[a] + extents[b] + min(extents[a], extents[b]) * communityClearance
            guard distance < wanted else { continue }

            // Two groups sitting on the same point have no direction to
            // separate along. Any choice will do provided it is the same one on
            // every machine, so it is derived from the pair rather than drawn.
            let direction: SIMD2<Double>
            if distance > 1e-9 {
              direction = delta / distance
            } else {
              let angle = Double(a &* 31 &+ b) * 2.399_963_229_728_653
              direction = SIMD2<Double>(cos(angle), sin(angle))
            }

            // Capped by the smaller neighbourhood's own size, which is what
            // decides where the pair comes to rest: uncapped, a handful of
            // entities overlapping a very large region is told to clear that
            // region's entire radius, and since the push is split by population
            // it is the handful that travels. Dozens of small groups then settle
            // in a ring at the edge of the canvas. Capped, a small group drifts
            // to the large one's edge and stops, and two large groups — where
            // the cap is large — still separate the whole way.
            let smaller = min(extents[a], extents[b])
            let push = min(wanted - distance, smaller) * communitySeparation

            // Split by population, so the smaller neighbourhood does most of
            // the moving. Without this a two-entity fragment would shove a
            // hundred-entity region across the map.
            let total = populations[a] + populations[b]
            groupShifts[a] -= direction * (push * populations[b] / total)
            groupShifts[b] += direction * (push * populations[a] / total)
          }
        }
      }

      for i in 0..<count where i != pinnedIndex {
        if let target = fieldTargets[i] {
          displacements[i] += (target - points[i]) * typeFieldStrength
        }
        if cohering, communities[i] >= 0, populations[communities[i]] > 1 {
          let offset = points[i] - centroids[communities[i]]
          let stray = simd_length(offset) - radii[communities[i]]
          if stray > 0 {
            displacements[i] -= (offset / simd_length(offset)) * stray * communityCohesion
          }
          displacements[i] += groupShifts[communities[i]]
        }
        displacements[i] -= points[i] * centerGravity
      }

      // Cooling: early steps may move a long way, later ones only settle.
      let progress = Double(step) / Double(steps)
      let temperature = 0.14 * pow(1 - progress, 1.5)
      for i in 0..<count where i != pinnedIndex {
        let magnitude = simd_length(displacements[i])
        guard magnitude > 1e-12 else { continue }
        points[i] += (displacements[i] / magnitude) * min(magnitude, temperature)
      }
    }
  }

  // MARK: - Canonical orientation

  /// A force layout is rotation- and reflection-invariant, so adding one entity
  /// can spin or mirror the whole map even though every neighbourhood survived.
  /// Neighbourhoods are what the user navigates by, but "work is over on the
  /// left" is worth keeping too, and it costs one pass: align the principal
  /// axis with the wide axis of the canvas, then resolve the two remaining
  /// ambiguities against the highest-degree nodes.
  static func orientCanonically(
    _ points: inout [SIMD2<Double>],
    coreIDs: [String],
    neighbors: [String: [(id: String, weight: Double)]],
    pinnedIndex: Int?
  ) {
    let count = points.count
    guard count > 2 else { return }

    let pivot = pinnedIndex.map { points[$0] } ?? points.reduce(.zero, +) / Double(count)

    var xx = 0.0
    var xy = 0.0
    var yy = 0.0
    for point in points {
      let delta = point - pivot
      xx += delta.x * delta.x
      xy += delta.x * delta.y
      yy += delta.y * delta.y
    }
    guard xx + yy > 1e-9 else { return }

    // Principal eigenvector of a 2×2 symmetric covariance matrix, closed form.
    let angle = 0.5 * atan2(2 * xy, xx - yy)
    let cosine = cos(-angle)
    let sine = sin(-angle)
    for i in 0..<count {
      let delta = points[i] - pivot
      points[i] =
        pivot
        + SIMD2<Double>(
          delta.x * cosine - delta.y * sine,
          delta.x * sine + delta.y * cosine)
    }

    // Rotation fixed the axis but not which end is which, and mirroring is
    // still free. Both are pinned to the most connected entities, which are the
    // landmarks a user would actually orient by.
    let ranked = coreIDs.enumerated().sorted {
      let lhs = (neighbors[$0.element] ?? []).count
      let rhs = (neighbors[$1.element] ?? []).count
      return lhs == rhs ? $0.element < $1.element : lhs > rhs
    }.map(\.offset)

    // Half a turn, not a mirror: the map keeps its handedness and the busiest
    // entity always ends up on the same side.
    if let primary = ranked.first(where: { abs(points[$0].x - pivot.x) > 1e-9 }),
      points[primary].x < pivot.x
    {
      for i in 0..<count {
        points[i] = pivot - (points[i] - pivot)
      }
    }
    if let secondary = ranked.first(where: { abs(points[$0].y - pivot.y) > 1e-9 }),
      points[secondary].y < pivot.y
    {
      for i in 0..<count {
        points[i].y = 2 * pivot.y - points[i].y
      }
    }
  }

  // MARK: - Fitting

  /// Maps the working box into normalized canvas coordinates.
  ///
  /// When there is an anchor it stays dead centre — "you" being the middle of
  /// your own map is the one positional promise worth keeping — so the fit is
  /// symmetric about it rather than a plain bounding box.
  private static func fit(
    points: [SIMD2<Double>],
    coreIDs: [String],
    pinnedIndex: Int?,
    area: CGRect
  ) -> [String: CGPoint] {
    guard !points.isEmpty else { return [:] }

    let center =
      pinnedIndex.map { points[$0] }
      ?? {
        var minimum = points[0]
        var maximum = points[0]
        for point in points {
          minimum = simd_min(minimum, point)
          maximum = simd_max(maximum, point)
        }
        return (minimum + maximum) / 2
      }()

    // Scale to the bulk, not to the bounding box.
    //
    // Even with detached islands parked, the main component keeps a handful of
    // loosely attached stragglers that drift a long way out, and letting them
    // set the scale squashes everything readable into the middle quarter of the
    // canvas. Fitting the full extent instead was tried on a real 1,097-entity
    // account and did exactly that.
    let radiiX = points.map { abs($0.x - center.x) }.sorted()
    let radiiY = points.map { abs($0.y - center.y) }.sorted()
    let cut = min(max(Int(Double(points.count) * fittedShare) - 1, 0), points.count - 1)
    let extentX = max(radiiX[cut], 1e-6)
    let extentY = max(radiiY[cut], 1e-6)

    // Mostly one scale for both axes, so the shape the simulation found is the
    // shape the user sees. But a graph with a strong principal axis — a chain,
    // or anything the orientation pass has just laid on its side — comes out
    // wide and flat, and a strictly uniform scale then leaves most of the
    // vertical canvas empty while packing names into a band too thin to read
    // them. A bounded stretch of the shorter axis spends that space without
    // distortion anyone can see.
    let fitX = Double(area.width) / 2 / extentX
    let fitY = Double(area.height) / 2 / extentY
    let uniform = min(fitX, fitY)
    let scaleX = min(fitX, uniform * maximumAspectStretch)
    let scaleY = min(fitY, uniform * maximumAspectStretch)

    var positions: [String: CGPoint] = [:]
    for (index, id) in coreIDs.enumerated() {
      let delta = points[index] - center
      let folded = softFold(
        SIMD2<Double>(
          delta.x * scaleX / (Double(area.width) / 2),
          delta.y * scaleY / (Double(area.height) / 2)))
      positions[id] = CGPoint(
        x: area.midX + CGFloat(folded.x * Double(area.width) / 2),
        y: area.midY + CGFloat(folded.y * Double(area.height) / 2))
    }
    return positions
  }

  /// Keeps the far tail on the canvas without touching the bulk.
  ///
  /// Fitting to the 98th percentile means the last 2% would otherwise land off
  /// the edge. Below `knee` this is exactly the identity, so almost every node
  /// sits precisely where the simulation put it; beyond it, the distance from
  /// the centre is compressed into the remaining margin.
  ///
  /// The compression is radial, not per-axis. Folding each axis on its own
  /// pushed every far node onto the same boundary x — and the separation pass
  /// then spaced that pile evenly, drawing a perfectly straight column of dots
  /// down the edge of the canvas that looked exactly like a rendering bug.
  /// Folding the radius preserves each node's direction, so the tail lands
  /// spread around the rim instead of stacked on one line.
  private static func softFold(_ offset: SIMD2<Double>) -> SIMD2<Double> {
    // Starting the compression well inside the rim spreads the tail over a
    // wide band instead of stacking it against the boundary, which is what
    // made the folded nodes read as a ridge rather than as a scatter.
    let knee = 0.72
    let radius = simd_length(offset)
    guard radius > knee, radius > 1e-12 else { return offset }
    let headroom = 1 - knee
    let folded = knee + headroom * tanh((radius - knee) / headroom)
    return offset * (folded / radius)
  }

  /// Pushes apart marks that landed close enough to hide each other's name.
  ///
  /// Relaxation optimises for relationships, not for legibility, and it will
  /// happily fold a chain so that entities several hops apart end up touching.
  /// A map whose entities are anonymous dots has lost the argument regardless
  /// of how good its structure is — on a 26-entity account, 16 of the names
  /// went missing before this pass existed.
  ///
  /// The target is a fraction of the spacing an even scatter would have, so it only ever
  /// resolves genuine crowding and never fights the layout for room. Movement
  /// is local, so neighbourhoods survive it.
  static func separateCrowdedMarks(
    _ positions: inout [String: CGPoint],
    coreIDs: [String],
    anchorID: String?,
    area: CGRect,
    passes: Int = 12
  ) {
    let count = coreIDs.count
    guard count > 1 else { return }

    // Spent where it buys something, withdrawn where it would cost more than
    // it returns. A small map shows every name, so it is worth spacing marks
    // generously. A thousand-entity map shows almost none at overview zoom, and
    // forcing even spacing there would flatten the density contrast that *is*
    // the structure — measured on a planted-community graph, holding the small
    // map's spacing at production scale dropped neighbourhood precision from
    // 0.74 to 0.52.
    let crowding = min(max((Double(count) - 60) / 340, 0), 1)
    let evenSpacing = sqrt(Double(area.width) * Double(area.height) / Double(count))
    let minimum = evenSpacing * (0.82 - 0.57 * crowding)
    guard minimum > 0 else { return }

    var points = coreIDs.map { positions[$0] ?? CGPoint(x: area.midX, y: area.midY) }
    let anchorIndex = anchorID.flatMap { coreIDs.firstIndex(of: $0) }

    for _ in 0..<passes {
      // Bucketed at the separation distance, so each node only measures against
      // the nine cells that could possibly hold something too close.
      var buckets: [Int: [Int]] = [:]
      func cell(_ point: CGPoint) -> (Int, Int) {
        (Int(floor(Double(point.x) / minimum)), Int(floor(Double(point.y) / minimum)))
      }
      for (index, point) in points.enumerated() {
        let (cx, cy) = cell(point)
        buckets[cx &* 73_856_093 ^ cy &* 19_349_663, default: []].append(index)
      }

      var moved = false
      for i in 0..<count {
        let (cx, cy) = cell(points[i])
        for dx in -1...1 {
          for dy in -1...1 {
            let key = (cx + dx) &* 73_856_093 ^ (cy + dy) &* 19_349_663
            for j in buckets[key] ?? [] where j > i {
              var delta = SIMD2<Double>(
                Double(points[j].x - points[i].x), Double(points[j].y - points[i].y))
              var distance = simd_length(delta)
              if distance < 1e-9 {
                // Exactly coincident: nudge along a deterministic axis. The
                // separation has to stay *below* the minimum or the guard
                // below rejects it and the pair stays stacked forever.
                delta = SIMD2<Double>(minimum / 2, 0)
                distance = minimum / 2
              }
              guard distance < minimum else { continue }
              let push = (delta / distance) * ((minimum - distance) / 2)
              if i != anchorIndex {
                points[i].x -= CGFloat(push.x)
                points[i].y -= CGFloat(push.y)
              }
              if j != anchorIndex {
                points[j].x += CGFloat(push.x)
                points[j].y += CGFloat(push.y)
              }
              moved = true
            }
          }
        }
      }
      if !moved { break }
    }

    let bounds = area.insetBy(dx: -area.width * 0.04, dy: -area.height * 0.04)
    for (index, id) in coreIDs.enumerated() {
      positions[id] = clamp(points[index], to: bounds)
    }
  }

  /// Leaves ride just outside their parent, fanned deterministically so a hub
  /// with nine of them reads as a burr rather than a stack.
  private static func placeLeaves(
    into positions: inout [String: CGPoint],
    identifiers: [String],
    roles: [String: Role],
    area: CGRect
  ) {
    var leavesByParent: [String: [String]] = [:]
    for id in identifiers {
      if case .leaf(let parentID) = roles[id] {
        leavesByParent[parentID, default: []].append(id)
      }
    }

    let stub = Double(min(area.width, area.height)) * 0.022
    for parentID in leavesByParent.keys.sorted() {
      guard let parent = positions[parentID] else { continue }
      let leaves = (leavesByParent[parentID] ?? []).sorted()
      // Fan outward from the map's centre so burrs grow away from the crowd
      // instead of back through their own hub.
      let outward = atan2(Double(parent.y - area.midY), Double(parent.x - area.midX))
      let spread = min(Double.pi * 1.4, 0.5 * Double(leaves.count))
      for (offset, id) in leaves.enumerated() {
        let fraction = leaves.count == 1 ? 0.5 : Double(offset) / Double(leaves.count - 1)
        // Deterministic scatter within each leaf's slot. Evenly spaced on a
        // fixed radius, a hub with thirty leaves drew a flawless arc of dots
        // across the map — the one shape in nature that is obviously a machine,
        // and on a real account it read as a rendering fault rather than as
        // thirty things that only relate to Singapore. The jitter stays inside
        // the slot, so the burr keeps its size and its parent.
        let slot = leaves.count == 1 ? spread : spread / Double(leaves.count - 1)
        let angle =
          outward - spread / 2 + spread * fraction
          + (stableFraction("leaf-angle-\(id)") - 0.5) * slot * 0.9
        // A second, shorter ring once a hub has more leaves than one ring can
        // hold without them touching.
        let ring = (1 + Double(offset / 12) * 0.55) * (0.78 + 0.44 * stableFraction("leaf-reach-\(id)"))
        positions[id] = clamp(
          CGPoint(
            x: parent.x + CGFloat(cos(angle) * stub * ring),
            y: parent.y + CGFloat(sin(angle) * stub * ring)),
          to: area.insetBy(dx: -area.width * 0.03, dy: -area.height * 0.03))
      }
    }
  }

  /// Entities with no relationships at all. They carry no spatial information,
  /// so scattering them through the middle would have the map assert structure
  /// that is not there. A faint outer halo says what is true: present, not
  /// connected to anything yet.
  /// Each group takes one place on the rim and its members cluster there.
  ///
  /// Stringing every entity along the perimeter one slot at a time produced
  /// visibly even rows and columns of dots down the edges of the canvas, which
  /// read as a rendering artefact rather than as content. Placing a
  /// three-entity island as one small clump says what is true — these three
  /// know each other and nothing else — and looks deliberate.
  static func haloPositions(groups: [[String]], area: CGRect) -> [String: CGPoint] {
    guard !groups.isEmpty else { return [:] }

    var positions: [String: CGPoint] = [:]
    let perRing = 44
    for (offset, group) in groups.enumerated() {
      let ring = offset / perRing
      let indexInRing = offset % perRing
      let occupancy = min(groups.count - ring * perRing, perRing)
      // Deterministic per-slot jitter, so the rim reads as scattered rather
      // than as a dotted rule drawn around the map.
      let wobble = (stableFraction("halo-\(group.first ?? "")") - 0.5) * 0.9
      let angle = 2 * Double.pi * (Double(indexInRing) + 0.5 + wobble) / Double(max(occupancy, 1))

      // Seated just outside where the structure actually reaches in *this*
      // direction, rather than on a fixed rim around everything.
      //
      // The map is not a disc and its shape changes with the account. A rim at
      // a constant multiple of the drawing area strands an unconnected entity
      // halfway across empty canvas whenever the structure happens to stop
      // early on that side — which is most sides, since the fit only guarantees
      // the *furthest* entities reach the edge. Following the silhouette keeps
      // the same claim (outside everything, connected to nothing) at a distance
      // that reads as deliberate instead of as debris.
      //
      // Depth still varies per seat: the band has to look scattered, or a run
      // of singletons draws an evenly spaced arc that reads as a rendering
      // artefact rather than as content.
      let depth = 0.98 + 0.16 * stableFraction("depth-\(group.first ?? "")")
      let spread = (1.0 + haloClearance + 0.03 * Double(ring)) * depth
      let halfWidth = Double(area.width) / 2 * spread
      let halfHeight = Double(area.height) / 2 * spread
      let reach = 1 / max(abs(cos(angle)) / halfWidth, abs(sin(angle)) / halfHeight)
      let seat = CGPoint(
        x: area.midX + CGFloat(cos(angle) * reach),
        y: area.midY + CGFloat(sin(angle) * reach))

      let clump = Double(min(area.width, area.height)) * 0.016
      for (memberIndex, id) in group.sorted().enumerated() {
        let memberAngle =
          stableFraction(id) * 2 * .pi + Double(memberIndex) * 2.399_963_229_728_653
        let radius = group.count == 1 ? 0 : clump * (0.6 + 0.4 * stableFraction("r-\(id)"))
        positions[id] = clamp(
          CGPoint(
            x: seat.x + CGFloat(cos(memberAngle) * radius),
            y: seat.y + CGFloat(sin(memberAngle) * radius)),
          to: CGRect(x: 0.02, y: 0.04, width: 0.96, height: 0.92))
      }
    }
    return positions
  }

  /// Deterministic 0..<1 from a string — the layout's only source of jitter,
  /// and hash-seeded `hashValue` would vary per launch.
  static func stableFraction(_ value: String) -> Double {
    var hash: UInt64 = 0xcbf2_9ce4_8422_2325
    for byte in value.utf8 {
      hash ^= UInt64(byte)
      hash = hash &* 0x0000_0100_0000_01b3
    }
    return Double(hash % 10_000) / 10_000
  }

  private static func clamp(_ point: CGPoint, to rect: CGRect) -> CGPoint {
    CGPoint(
      x: min(max(point.x, rect.minX), rect.maxX),
      y: min(max(point.y, rect.minY), rect.maxY))
  }
}

// MARK: - Barnes–Hut

/// Approximates all-pairs repulsion in O(n log n).
///
/// The atlas is built inside a SwiftUI `init`, so the whole layout has to fit
/// in a frame's worth of main-thread time. Exact repulsion over ~1,000 nodes
/// for a couple of hundred steps does not; this does, and at layout accuracy
/// nobody can see the difference.
private struct Quadtree {
  private struct Cell {
    var centerOfMass: SIMD2<Double> = .zero
    var mass: Double = 0
    var origin: SIMD2<Double> = .zero
    var size: Double = 0
    /// Index of the single body in a leaf cell, or -1 once it has subdivided.
    var body: Int = -1
    /// That body's own position. The cell's centre of mass already averages in
    /// every later arrival, so it cannot be used to re-place the occupant when
    /// the cell subdivides.
    var bodyPoint: SIMD2<Double> = .zero
    var children: SIMD4<Int32> = SIMD4<Int32>(repeating: -1)
    var isLeaf: Bool { children[0] < 0 && children[1] < 0 && children[2] < 0 && children[3] < 0 }

    func contains(_ point: SIMD2<Double>) -> Bool {
      point.x >= origin.x && point.x <= origin.x + size
        && point.y >= origin.y && point.y <= origin.y + size
    }
  }

  private var cells: [Cell] = []

  init(points: [SIMD2<Double>]) {
    guard !points.isEmpty else { return }

    var minimum = points[0]
    var maximum = points[0]
    for point in points {
      minimum = simd_min(minimum, point)
      maximum = simd_max(maximum, point)
    }
    let span = max(maximum.x - minimum.x, maximum.y - minimum.y)
    let size = max(span, 1e-6) * 1.02

    cells.reserveCapacity(points.count * 2)
    cells.append(Cell(origin: minimum, size: size))
    for (index, point) in points.enumerated() {
      insert(point: point, body: index, into: 0, depth: 0)
    }
  }

  private mutating func insert(point: SIMD2<Double>, body: Int, into cellIndex: Int, depth: Int) {
    cells[cellIndex].mass += 1
    cells[cellIndex].centerOfMass += point

    // Coincident or near-coincident bodies would subdivide forever. At this
    // depth the cell is far smaller than any visible distance, so they simply
    // share it and repel each other as one mass.
    guard depth < 22 else { return }

    if cells[cellIndex].isLeaf {
      let occupant = cells[cellIndex].body
      if occupant < 0 {
        cells[cellIndex].body = body
        cells[cellIndex].bodyPoint = point
        return
      }
      // Push the sitting tenant down a level, then fall through to place the
      // newcomer alongside it.
      let occupantPoint = cells[cellIndex].bodyPoint
      cells[cellIndex].body = -1
      subdivideAndInsert(point: occupantPoint, body: occupant, cellIndex: cellIndex, depth: depth)
    }
    subdivideAndInsert(point: point, body: body, cellIndex: cellIndex, depth: depth)
  }

  private mutating func subdivideAndInsert(
    point: SIMD2<Double>, body: Int, cellIndex: Int, depth: Int
  ) {
    let origin = cells[cellIndex].origin
    let half = cells[cellIndex].size / 2
    let quadrant = (point.x >= origin.x + half ? 1 : 0) + (point.y >= origin.y + half ? 2 : 0)

    var childIndex = Int(cells[cellIndex].children[quadrant])
    if childIndex < 0 {
      let childOrigin = SIMD2<Double>(
        origin.x + (quadrant % 2 == 1 ? half : 0),
        origin.y + (quadrant >= 2 ? half : 0))
      cells.append(Cell(origin: childOrigin, size: half))
      childIndex = cells.count - 1
      cells[cellIndex].children[quadrant] = Int32(childIndex)
    }
    insert(point: point, body: body, into: childIndex, depth: depth + 1)
  }

  /// Sum of repulsive force on `point`, opening a cell only when it is close
  /// enough that its internal structure could matter.
  ///
  /// `stack` is supplied by the caller and reused across every node in a step;
  /// allocating a fresh traversal buffer per node per step costs more than the
  /// force computation it serves.
  func repulsion(
    on point: SIMD2<Double>, kSquared: Double, theta: Double, stack: inout [Int]
  ) -> SIMD2<Double> {
    guard !cells.isEmpty else { return .zero }
    var force = SIMD2<Double>.zero
    stack.removeAll(keepingCapacity: true)
    stack.append(0)
    while let cellIndex = stack.popLast() {
      let cell = cells[cellIndex]
      guard cell.mass > 0 else { continue }

      // A cell holding the query point holds the query point's own mass, and
      // approximating it would have a node repel itself — with `theta` this
      // loose, that happens on the root cell for any node out near a corner.
      // Such a cell is always opened instead, down to the leaf the node lives
      // in, which is skipped outright.
      if cell.contains(point) {
        guard !cell.isLeaf else { continue }
        for quadrant in 0..<4 where cell.children[quadrant] >= 0 {
          stack.append(Int(cell.children[quadrant]))
        }
        continue
      }

      let centerOfMass = cell.centerOfMass / cell.mass
      let delta = point - centerOfMass
      let distance = simd_length(delta)
      guard distance > 1e-9 else { continue }

      if cell.isLeaf || cell.size / distance < theta {
        force += (delta / distance) * (kSquared * cell.mass / distance)
      } else {
        for quadrant in 0..<4 where cell.children[quadrant] >= 0 {
          stack.append(Int(cell.children[quadrant]))
        }
      }
    }
    return force
  }
}
