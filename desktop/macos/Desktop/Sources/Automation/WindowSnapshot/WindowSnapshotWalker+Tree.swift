import CoreGraphics
import CryptoKit
import Foundation

extension WindowSnapshotWalker {
  struct WalkResult {
    var nodes: [WindowSnapshotNode] = []
    var visited = 0
    var stopReason: WindowSnapshot.StopReason?
    /// Some branch went deeper than the depth limit; the walk went on elsewhere.
    var depthTruncated = false
    /// Children of oversized containers that were not read; the walk went on.
    var childrenOmitted = 0
    /// Accessibility switched off mid-walk: the whole read fails.
    var fatal: WindowSnapshotFailure?
  }

  /// Read first, alone, so a secure field is known before anything else is asked of it.
  static var identityAttributes: [String] { [AXName.role, AXName.subrole] }

  /// Everything else but `AXValue`, which is read only for value-bearing,
  /// non-secure roles. A secure field gets neither its value nor its length.
  static func detailAttributes(isSecure: Bool) -> [String] {
    var names = [
      AXName.title, AXName.description, AXName.identifier, AXName.placeholder, AXName.enabled, AXName.focused,
      AXName.position, AXName.size,
    ]
    if !isSecure { names.append(AXName.numberOfCharacters) }
    return names
  }

  func walkWindow(_ window: Element, bounds: CGRect, request: WindowSnapshotRequest, deadline: TimeInterval)
    -> WalkResult
  {
    var result = WalkResult()
    let limits = request.limits
    do {
      let top = try children(of: window, role: "AXWindow", limits: limits, into: &result)
      for child in top.elements where result.stopReason == nil {
        try visit(
          child.element, depth: 1, parentDepth: 0, emittedDepth: 0, path: [.child(child.index)], bounds: bounds,
          limits: limits, deadline: deadline, into: &result)
      }
    } catch {
      result.fatal = Self.failure(error)
    }
    if result.stopReason == nil, result.depthTruncated { result.stopReason = .depthLimit }
    if result.stopReason == nil, result.childrenOmitted > 0 { result.stopReason = .childLimit }
    return result
  }

  /// A container's children within the per-container cap and the visit budget:
  /// all of them, or its first and last ones. What is left out is counted and
  /// the walk carries on; only an exhausted visit budget stops it.
  private func children(of element: Element, role: String, limits: WindowSnapshotLimits, into result: inout WalkResult)
    throws(AccessibilitySourceError) -> AccessibilityChildren<Element>
  {
    let budget = min(limits.maxChildrenPerContainer, max(0, limits.maxVisited - result.visited))
    let tail = budget / 2
    let fetched = try source.children(
      of: element, preferVisible: Self.visibleRowContainers.contains(role), head: budget - tail, tail: tail)
    if fetched.elements.count < fetched.total {
      if limits.maxVisited - result.visited <= 0 {
        result.stopReason = .visitLimit
      } else {
        result.childrenOmitted += fetched.total - fetched.elements.count
      }
    }
    return fetched
  }

  /// `depth` is the raw accessibility depth; `parentDepth` counts only the
  /// informative ancestors, which is what `maxDepth` limits.
  private func visit(
    _ element: Element, depth: Int, parentDepth: Int, emittedDepth: Int, path: [WindowSnapshotNode.PathStep],
    bounds: CGRect,
    limits: WindowSnapshotLimits, deadline: TimeInterval, into result: inout WalkResult
  ) throws(AccessibilitySourceError) {
    guard result.stopReason == nil else { return }
    if isCancelled() {
      result.stopReason = .cancelled
      return
    }
    if now() >= deadline {
      result.stopReason = .deadline
      return
    }
    if result.visited >= limits.maxVisited {
      result.stopReason = .visitLimit
      return
    }
    result.visited += 1

    let read: ElementRead
    do {
      read = try readElement(element, limits: limits)
    } catch .timedOut {
      // One timeout costs a quarter second; four hundred of them would not.
      result.stopReason = .appNotResponding
      return
    } catch .invalidElement {
      return
    } catch {
      throw error
    }

    let ownDepth = read.isWrapper ? parentDepth : parentDepth + 1
    var children = AccessibilityChildren<Element>(elements: [], total: 0, visibleOnly: false)
    if !read.isSecure {
      do {
        if ownDepth >= limits.maxDepth || depth >= limits.maxRawDepth {
          // Only the count: nothing below the depth limit is fetched.
          let count = try source.children(of: element, preferVisible: false, head: 0, tail: 0)
          if count.total > 0 { result.depthTruncated = true }
          children.total = count.total
        } else {
          children = try self.children(of: element, role: read.role, limits: limits, into: &result)
        }
      } catch .timedOut {
        result.stopReason = .appNotResponding
      } catch .invalidElement {
        children.total = 0
      } catch {
        throw error
      }
    }

    // Frames are kept relative to the window so the fingerprint survives a move.
    let frame = read.frame.map { $0.offsetBy(dx: -bounds.minX, dy: -bounds.minY) }
    let windowArea = CGRect(origin: .zero, size: bounds.size)
    let invisible =
      frame.map { $0.width <= 0 || $0.height <= 0 || (!windowArea.isEmpty && !$0.intersects(windowArea)) } ?? false
    if invisible && children.total == 0 { return }

    var childEmittedDepth = emittedDepth
    if read.isEmitted {
      if result.nodes.count >= limits.maxNodes {
        result.stopReason = .nodeLimit
        return
      }
      result.nodes.append(
        WindowSnapshotNode(
          role: read.role, subrole: read.subrole, label: read.label, value: read.value,
          identifier: read.identifier, actions: read.actions, isSecure: read.isSecure, isFocused: read.isFocused,
          isDisabled: read.isDisabled, path: path, frame: frame, depth: emittedDepth))
      childEmittedDepth += 1
    }
    for child in children.elements {
      guard result.stopReason == nil else { break }
      try visit(
        child.element, depth: depth + 1, parentDepth: ownDepth, emittedDepth: childEmittedDepth,
        path: path + [children.visibleOnly ? .visibleRow(child.index) : .child(child.index)], bounds: bounds,
        limits: limits, deadline: deadline, into: &result)
    }
  }

  // MARK: - One element

  private struct ElementRead {
    var role = "AXUnknown"
    var subrole: String?
    var label: WindowSnapshotAppText?
    var value: WindowSnapshotNode.Value?
    var identifier: String?
    var actions: [String] = []
    var isSecure = false
    var isFocused = false
    var isDisabled = false
    var frame: CGRect?
    var isEmitted = false
    /// An anonymous wrapper: costs no depth and is not emitted.
    var isWrapper = false
  }

  private func readElement(_ element: Element, limits: WindowSnapshotLimits) throws(AccessibilitySourceError)
    -> ElementRead
  {
    let identity = try source.attributes(Self.identityAttributes, of: element)
    var read = ElementRead()
    read.role = identity[AXName.role]?.string.flatMap(Self.token) ?? "AXUnknown"
    read.subrole = identity[AXName.subrole]?.string.flatMap(Self.token)
    read.isSecure = read.role == "AXSecureTextField" || read.subrole == "AXSecureTextField"
    let attributes = try source.attributes(Self.detailAttributes(isSecure: read.isSecure), of: element)
    read.isFocused = attributes[AXName.focused]?.bool == true
    read.isDisabled = attributes[AXName.enabled]?.bool == false
    read.identifier = attributes[AXName.identifier]?.string.map(WindowSnapshotText.sanitize).flatMap {
      $0.isEmpty ? nil : $0
    }
    // A long label (a Catalyst message body sits in AXDescription) is left
    // out like a long value: only its length is sent.
    read.label = [AXName.title, AXName.description, AXName.placeholder].lazy
      .compactMap { attributes[$0]?.string.map(WindowSnapshotText.appText) }
      .first { !$0.isEmpty }
      .flatMap { WindowSnapshotText.bounded($0, limits: limits) }
    if case .point(let position)? = attributes[AXName.position], case .size(let size)? = attributes[AXName.size] {
      read.frame = CGRect(origin: position, size: size)
    }

    if !read.isSecure, Self.valueRoles.contains(read.role) {
      if case .number(let length)? = attributes[AXName.numberOfCharacters], length.isFinite,
        length > Double(limits.maxTextCharacters), length < Double(Int.max)
      {
        read.value = .omitted(characters: Int(length))
      } else {
        let raw = try source.attributes([AXName.value], of: element)[AXName.value]
        read.value = Self.value(raw, role: read.role, limits: limits)
      }
    }

    let axActions = Set(try source.actionNames(of: element))
    var actions: [String] = []
    for (axAction, name) in Self.actionVocabulary where axActions.contains(axAction) && !actions.contains(name) {
      actions.append(name)
    }
    if !read.isSecure, Self.textRoles.contains(read.role), try source.isValueSettable(element) {
      actions.append("set")
    }
    read.actions = actions
    read.isWrapper =
      Self.wrapperRoles.contains(read.role) && read.label == nil && read.value == nil && read.identifier == nil
      && actions.allSatisfy { $0 == "menu" } && !read.isSecure
    read.isEmitted =
      !read.isWrapper
      && (read.label != nil || read.value != nil || !actions.isEmpty || read.isSecure
        || Self.structuralRoles.contains(read.role))
    return read
  }

  static func value(_ raw: AccessibilityAttributeValue?, role: String, limits: WindowSnapshotLimits)
    -> WindowSnapshotNode.Value?
  {
    switch raw {
    case .string(let text)?:
      let clean = WindowSnapshotText.appText(text)
      if clean.isEmpty { return nil }
      if text.count > limits.maxTextCharacters { return .omitted(characters: text.count) }
      return .text(clean)
    case .bool(let flag)?:
      return .toggle(flag)
    case .number(let number)?:
      guard number.isFinite else { return nil }
      if toggleRoles.contains(role) { return .toggle(number != 0) }
      return .number(number.rounded() == number && abs(number) < 1e15 ? String(Int64(number)) : String(number))
    default:
      return nil
    }
  }

  /// Roles and subroles are tokens: anything else from the app is dropped.
  static func token(_ raw: String) -> String? {
    let allowed = raw.unicodeScalars.allSatisfy { CharacterSet.alphanumerics.contains($0) || $0 == "_" }
    return allowed && !raw.isEmpty && raw.count <= 64 ? raw : nil
  }

  // MARK: - References and fingerprints

  /// `a:<identifier>` when unique in this snapshot, else `n:<role>:"<label>"`
  /// when that pair is unique and short, else the child-index path. Assigned
  /// after the walk so uniqueness is known across the whole window.
  static func assigningReferences(_ nodes: [WindowSnapshotNode], limits: WindowSnapshotLimits)
    -> [WindowSnapshotNode]
  {
    var identifierCounts: [String: Int] = [:]
    var nameCounts: [String: Int] = [:]
    for node in nodes {
      if let identifier = node.identifier { identifierCounts[identifier, default: 0] += 1 }
      if let label = node.label?.text { nameCounts[nameKey(node.role, label), default: 0] += 1 }
    }
    return nodes.map { node in
      var node = node
      if let identifier = node.identifier, identifierCounts[identifier] == 1, isReferenceSafe(identifier) {
        node.ref = "a:\(identifier)"
      } else if let label = node.label?.text, label.count <= limits.maxReferenceLabelCharacters,
        nameCounts[nameKey(node.role, label)] == 1
      {
        node.ref = "n:\(node.role):\(WindowSnapshot.quoted(label))"
      } else {
        node.ref = WindowSnapshot.pathRef(node.path)
      }
      node.fingerprint = fingerprint(node)
      return node
    }
  }

  private static func nameKey(_ role: String, _ label: String) -> String { "\(role)\u{1F}\(label)" }

  private static func isReferenceSafe(_ identifier: String) -> Bool {
    identifier.count <= 80
      && identifier.unicodeScalars.allSatisfy { !$0.properties.isWhitespace && $0 != "\"" && $0 != "\\" }
  }

  /// First four bytes of SHA-256 over role, subrole, label and the frame
  /// relative to the window rounded to 32 pt, so moving the window keeps it
  /// and a changed control does not.
  static func fingerprint(_ node: WindowSnapshotNode) -> String {
    let bucket =
      node.frame.map { frame in
        [frame.minX, frame.minY, frame.width, frame.height]
          .map { $0.isFinite ? String(Int(($0 / 32).rounded())) : "x" }
          .joined(separator: ",")
      } ?? "-"
    let label: String
    switch node.label {
    case .text(let text)?: label = text
    case .omitted(let characters)?: label = "~\(characters)"
    case nil: label = ""
    }
    let material = [node.role, node.subrole ?? "", label, bucket].joined(separator: "|")
    return SHA256.hash(data: Data(material.utf8)).prefix(4).map { String(format: "%02x", $0) }.joined()
  }
}
