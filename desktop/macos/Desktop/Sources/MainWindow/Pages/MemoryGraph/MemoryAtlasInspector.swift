import AppKit
import OmiTheme
import SwiftUI

// MARK: - Node Inspector

/// One memory backing a selected entity, flattened so the atlas surface does
/// not depend on the memories layer. The panel renders these directly instead
/// of navigating away, which is what makes the Brain Map a place you can stay
/// in while reading what an entity is made of.
struct MemoryAtlasEvidence: Identifiable, Equatable {
  let id: String
  let content: String
  let createdAt: Date?

  /// Resolves cited memory ids against whatever the memories layer has loaded,
  /// preserving that order so the inspector reads newest-first like the list.
  /// Ids with no loaded memory are simply absent — the panel reports the gap
  /// rather than the surface pretending the entity has less evidence than it
  /// does.
  static func resolve(_ ids: [String], in memories: [ServerMemory]) -> [MemoryAtlasEvidence] {
    let wanted = Set(ids)
    guard !wanted.isEmpty else { return [] }
    return memories.filter { wanted.contains($0.id) }.map {
      MemoryAtlasEvidence(id: $0.id, content: $0.content, createdAt: $0.createdAt)
    }
  }
}

/// What the inspector is describing.
///
/// The Brain Map has two things worth clicking — the entities and the
/// connections between them — and both answer the same three questions: what
/// is this, what does it touch, and which memories produced it. One panel
/// shape for both keeps traversal continuous instead of making a relationship
/// a dead end.
enum MemoryAtlasInspectorSubject: Equatable {
  case entity(title: String, typeName: String?, connectionSummary: String)
  case relationship(sourceLabel: String, targetLabel: String, verb: String)

  var title: String {
    switch self {
    case .entity(let title, _, _):
      return title
    case .relationship(let sourceLabel, let targetLabel, _):
      return "\(sourceLabel) → \(targetLabel)"
    }
  }

  var subtitle: String {
    switch self {
    case .entity(_, let typeName, let connectionSummary):
      return [typeName, connectionSummary].compactMap { $0 }.joined(separator: " · ")
    case .relationship(_, _, let verb):
      return verb
    }
  }

  /// Header for the section listing what this subject connects to.
  var relatedSectionTitle: String {
    switch self {
    case .entity: return "Connections"
    case .relationship: return "Between"
    }
  }
}

/// Right-hand inspector for the current selection.
///
/// Replaces the "View evidence" jump to Memories: selecting a node used to
/// change pages, which lost the camera, the time cursor, and the selection.
struct MemoryAtlasDetailPanel: View {
  let subject: MemoryAtlasInspectorSubject
  let accent: Color
  let related: [MemoryAtlasRelationshipRow]
  let evidence: [MemoryAtlasEvidence]
  let evidenceIsLoading: Bool
  let unresolvedEvidenceCount: Int
  let onOpenRelated: (MemoryAtlasRelationshipRow) -> Void
  /// Opens a cited memory on the Memories page with its detail panel showing.
  /// The inspector deliberately shows the whole memory in place, but a memory
  /// is also a thing you act on — edit it, check its provenance, delete it —
  /// and none of that belongs in a graph inspector.
  let onOpenMemory: (MemoryAtlasEvidence) -> Void
  /// Present once the user has followed a connection. Traversal without a way
  /// back turns every hop into a dead end you can only escape by hunting for
  /// the previous dot on the canvas.
  let onBack: (() -> Void)?
  let onFocus: () -> Void
  let onClose: () -> Void

  @State private var hoveredRelatedID: String?
  @State private var hoveredEvidenceID: String?

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      header

      Divider().overlay(Ink.separator.opacity(0.2))

      ScrollView {
        VStack(alignment: .leading, spacing: 18) {
          if !related.isEmpty {
            section(subject.relatedSectionTitle) {
              VStack(alignment: .leading, spacing: 2) {
                ForEach(related) { row in
                  relatedRow(row)
                }
              }
              // Rows carry their own inset so the hover fill reads as a
              // target; pulling it back keeps their text on the same margin
              // as the section title.
              .padding(.horizontal, -6)
            }
          }

          section("From your memories") {
            evidenceSection
          }
        }
        .padding(16)
      }
    }
    .frame(width: 320)
    .background(Ink.rowFill)
    .overlay(alignment: .leading) {
      Rectangle().fill(Ink.separator.opacity(0.25)).frame(width: 1)
    }
    .accessibilityIdentifier("memory_atlas_detail_panel")
  }

  @ViewBuilder
  private var evidenceSection: some View {
    if evidenceIsLoading && evidence.isEmpty {
      HStack(spacing: 7) {
        ProgressView()
          .controlSize(.small)
          .tint(Ink.secondary)
        Text("Reading your memories…")
          .scaledFont(size: 11)
          .foregroundColor(Ink.secondary)
      }
    } else if evidence.isEmpty && unresolvedEvidenceCount == 0 {
      Text("Source memories are still being linked for this entity.")
        .scaledFont(size: 11)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
    } else {
      ForEach(evidence) { item in
        evidenceRow(item)
      }
      if unresolvedEvidenceCount > 0 {
        // Evidence resolves against the full local cache, so a remaining gap
        // means the cited memory genuinely is not on this device — not that
        // the list simply had not paged far enough yet.
        Text(
          "\(unresolvedEvidenceCount) cited memor\(unresolvedEvidenceCount == 1 ? "y" : "ies") could not be found on this device"
        )
        .scaledFont(size: 10)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private var header: some View {
    HStack(alignment: .top, spacing: 10) {
      if let onBack {
        Button(action: onBack) {
          Image(systemName: "chevron.left")
            .scaledFont(size: 11, weight: .semibold)
            .foregroundColor(Ink.secondary)
            .frame(width: 22, height: 30)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Back to the previous entity")
        .accessibilityIdentifier("memory_atlas_inspector_back")
      }

      Circle()
        .fill(accent.opacity(0.14))
        .overlay(Circle().stroke(accent, lineWidth: 1.5))
        .frame(width: 30, height: 30)

      VStack(alignment: .leading, spacing: 3) {
        Text(subject.title)
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
        Text(subject.subtitle)
          .scaledFont(size: 11)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 4)

      Button(action: onFocus) {
        Image(systemName: "scope")
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(Ink.secondary)
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Center the map on this entity")
      .accessibilityIdentifier("memory_atlas_focus_selection")

      Button(action: onClose) {
        Image(systemName: "xmark")
          .scaledFont(size: 10, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Clear selection (Esc)")
      .accessibilityIdentifier("memory_atlas_clear_selection")
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 14)
  }

  @ViewBuilder
  private func section<Content: View>(
    _ title: String,
    @ViewBuilder content: () -> Content
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title.uppercased())
        .scaledFont(size: 9.5, weight: .semibold)
        .foregroundColor(Ink.secondary)
        .tracking(0.6)
      content()
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  /// A connection is a way through the graph, not a caption. Clicking one
  /// moves the inspector to the entity on the other end, so following a chain
  /// of relationships never requires hunting for the next dot on the canvas.
  private func relatedRow(_ row: MemoryAtlasRelationshipRow) -> some View {
    let isHovered = hoveredRelatedID == row.id
    return Button {
      onOpenRelated(row)
    } label: {
      HStack(alignment: .top, spacing: 8) {
        Circle()
          .fill(row.accent)
          .frame(width: 5, height: 5)
          .padding(.top, 5)
        VStack(alignment: .leading, spacing: 1) {
          Text(row.otherLabel)
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(isHovered ? Ink.primary : Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
          Text(row.relationship)
            .scaledFont(size: 10)
            .foregroundColor(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: 4)
        Image(systemName: "chevron.right")
          .scaledFont(size: 9, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .opacity(isHovered ? 1 : 0)
          .padding(.top, 3)
      }
      .padding(.vertical, 5)
      .padding(.horizontal, 6)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: 7, style: .continuous)
          .fill(isHovered ? Ink.rowFill.opacity(0.7) : Color.clear)
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      if hovering {
        hoveredRelatedID = row.id
      } else if hoveredRelatedID == row.id {
        hoveredRelatedID = nil
      }
    }
    .help("Open \(row.otherLabel)")
    .accessibilityIdentifier("memory_atlas_connection_row")
  }

  private func evidenceRow(_ item: MemoryAtlasEvidence) -> some View {
    let isHovered = hoveredEvidenceID == item.id
    return Button {
      onOpenMemory(item)
    } label: {
      VStack(alignment: .leading, spacing: 4) {
        Text(item.content)
          .scaledFont(size: 11.5)
          .foregroundColor(isHovered ? Ink.primary : Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: .infinity, alignment: .leading)
        // The date holds this row whether or not the cursor is here, so the
        // "Open" affordance can fade in without the row changing height.
        HStack(spacing: 4) {
          if let createdAt = item.createdAt {
            Text(createdAt.formatted(date: .abbreviated, time: .shortened))
              .scaledFont(size: 9.5)
              .foregroundColor(Ink.secondary)
          }
          Spacer(minLength: 4)
          HStack(spacing: 3) {
            Text("Open")
              .scaledFont(size: 9.5, weight: .medium)
            Image(systemName: "arrow.up.right")
              .scaledFont(size: 8, weight: .semibold)
          }
          .foregroundColor(Ink.secondary)
          .opacity(isHovered ? 1 : 0)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(10)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(Ink.rowFill.opacity(isHovered ? 0.95 : 0.6))
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      if hovering {
        hoveredEvidenceID = item.id
      } else if hoveredEvidenceID == item.id {
        hoveredEvidenceID = nil
      }
    }
    .help("Open this memory on the Memories page")
    .accessibilityIdentifier("memory_atlas_evidence_row")
  }
}

struct MemoryAtlasRelationshipRow: Identifiable, Equatable {
  let id: String
  /// Where clicking this row goes. Without it the inspector could name the
  /// entity on the other end but not open it.
  let otherNodeID: String
  let otherLabel: String
  let relationship: String
  let accent: Color
}

/// Picking a painted connection out of the atlas.
///
/// Lives outside the view so the two rules that matter — a line is only picked
/// when the click is genuinely on it, and the nearest one wins — are testable
/// without a window or a gesture.
enum MemoryAtlasHitTesting {
  struct Segment {
    let id: String
    let start: CGPoint
    let end: CGPoint
  }

  static func distance(from point: CGPoint, toSegmentFrom start: CGPoint, to end: CGPoint) -> CGFloat {
    let run = end.x - start.x
    let rise = end.y - start.y
    let lengthSquared = run * run + rise * rise
    // A zero-length segment is a point; projecting onto it would divide by zero.
    guard lengthSquared > 0 else { return hypot(point.x - start.x, point.y - start.y) }
    let projection = ((point.x - start.x) * run + (point.y - start.y) * rise) / lengthSquared
    let clamped = min(1, max(0, projection))
    let nearest = CGPoint(x: start.x + clamped * run, y: start.y + clamped * rise)
    return hypot(point.x - nearest.x, point.y - nearest.y)
  }

  /// How far off a painted line a click may land and still count, in points.
  /// Connections are drawn under 2pt wide, so this is forgiveness for aim, not
  /// a hit area wide enough to steal clicks from a neighbouring line.
  static let connectionTolerance: CGFloat = 5

  static func nearestSegment(
    to point: CGPoint,
    among segments: [Segment],
    within tolerance: CGFloat
  ) -> String? {
    var best: (id: String, distance: CGFloat)?
    for segment in segments {
      let distance = distance(from: point, toSegmentFrom: segment.start, to: segment.end)
      guard distance <= tolerance else { continue }
      if best.map({ distance < $0.distance }) ?? true {
        best = (segment.id, distance)
      }
    }
    return best?.id
  }
}
