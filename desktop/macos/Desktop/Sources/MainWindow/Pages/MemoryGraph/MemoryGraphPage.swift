import OmiSupport
import OmiTheme
import SceneKit
import SwiftUI

// MARK: - Memory Graph Page

struct MemoryGraphPage: View {
  @ObservedObject var viewModel: MemoryGraphViewModel

  var body: some View {
    ZStack {
      // Full-bleed background + 3D scene
      OmiColors.backgroundSecondary.ignoresSafeArea()

      if !viewModel.isEmpty {
        MemoryGraphSceneView(viewModel: viewModel)
          .ignoresSafeArea()
      }

      // Minimal floating controls — no boxes, no backgrounds. (The Brain Map is
      // a Memory tab now, not a modal, so there's no close button.)
      VStack {
        HStack {
          Spacer()

          // Rebuild control: while rebuilding it just dims and disables — the
          // single centered spinner below is the only progress indicator, so
          // the header never shows a second spinner of its own.
          Button {
            Task { await viewModel.rebuildGraph() }
          } label: {
            Image(systemName: "arrow.clockwise")
              .scaledFont(size: OmiType.body)
              .foregroundColor(.white.opacity(viewModel.isRebuilding ? 0.2 : 0.5))
              .frame(width: 28, height: 28)
          }
          .buttonStyle(.plain)
          .disabled(viewModel.isRebuilding)
          .help("Rebuild graph")
        }
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.top, OmiSpacing.md)

        Spacer()
      }

      // Exactly one status view: a single centered spinner while loading or
      // rebuilding, otherwise an empty-state message — never a perpetual spinner
      // (the empty case used to spin forever because there was no exit).
      if viewModel.isLoading || viewModel.isRebuilding {
        ProgressView()
          .scaleEffect(1.2)
          .tint(.white.opacity(0.4))
      } else if viewModel.isEmpty {
        VStack(spacing: OmiSpacing.sm) {
          Image(systemName: "brain")
            .scaledFont(size: OmiType.heading)
            .foregroundColor(.white.opacity(0.3))
          Text("Brain map will appear once enough linked memories are available.")
            .scaledFont(size: 12.5)
            .foregroundColor(.white.opacity(0.5))
            .multilineTextAlignment(.center)
        }
        .padding(OmiSpacing.lg)
      }
    }
    .task {
      await viewModel.prepareGraph()
    }
  }
}

struct MemoryGraphInlineCard: View {
  @ObservedObject var viewModel: MemoryGraphViewModel

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(alignment: .center, spacing: OmiSpacing.md) {
        Text("Brain Map")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Button {
          Task { await viewModel.rebuildGraph() }
        } label: {
          Image(systemName: "arrow.clockwise")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(viewModel.isRebuilding ? OmiColors.textTertiary : OmiColors.textSecondary)
            .frame(width: 32, height: 32)
            .omiControlSurface(fill: OmiColors.backgroundRaised, radius: 12)
        }
        .buttonStyle(.plain)
        .disabled(viewModel.isRebuilding)
        .help("Rebuild brain map")
      }

      ZStack {
        OmiColors.backgroundSecondary

        if !viewModel.isEmpty {
          MemoryGraphSceneView(viewModel: viewModel)
        }

        if viewModel.isLoading || viewModel.isRebuilding {
          ProgressView()
            .scaleEffect(1.1)
            .tint(.white.opacity(0.45))
        } else if viewModel.isEmpty {
          VStack(spacing: OmiSpacing.sm) {
            Image(systemName: "brain")
              .scaledFont(size: OmiType.heading)
              .foregroundColor(OmiColors.textTertiary)
            Text("Brain map will appear once enough linked memories are available.")
              .scaledFont(size: 12.5)
              .foregroundColor(OmiColors.textSecondary)
              .multilineTextAlignment(.center)
          }
          .padding(OmiSpacing.lg)
        }
      }
      .frame(height: 350)
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.sectionRadius, style: .continuous))
    }
    .padding(OmiSpacing.lg)
    .omiPanel(
      fill: OmiColors.backgroundSecondary, radius: 24, stroke: OmiColors.border.opacity(0.14),
      shadowOpacity: 0.14, shadowRadius: 12, shadowY: 8
    )
    .task {
      await viewModel.prepareGraph()
    }
  }
}

// MARK: - SceneKit View

struct MemoryGraphSceneView: NSViewRepresentable {
  @ObservedObject var viewModel: MemoryGraphViewModel

  func makeNSView(context: Context) -> SCNView {
    let scnView = SCNView()
    scnView.scene = viewModel.scene
    scnView.pointOfView = viewModel.cameraNode
    scnView.allowsCameraControl = true
    scnView.autoenablesDefaultLighting = false  // We set up our own lights
    scnView.backgroundColor = NSColor(
      red: 0x1A / 255.0, green: 0x1A / 255.0, blue: 0x1A / 255.0, alpha: 1.0)  // Match OmiColors.backgroundSecondary
    scnView.antialiasingMode = .multisampling2X  // Lighter AA
    scnView.preferredFramesPerSecond = 30  // Cap render rate

    // Set up delegate for animation
    scnView.delegate = context.coordinator

    return scnView
  }

  func updateNSView(_ nsView: SCNView, context: Context) {
    // Update scene if needed
  }

  func makeCoordinator() -> Coordinator {
    Coordinator(viewModel: viewModel)
  }

  class Coordinator: NSObject, SCNSceneRendererDelegate {
    let viewModel: MemoryGraphViewModel
    private var lastUpdateTime: TimeInterval = 0

    init(viewModel: MemoryGraphViewModel) {
      self.viewModel = viewModel
    }

    func renderer(_ renderer: any SCNSceneRenderer, updateAtTime time: TimeInterval) {
      // Throttle to ~30fps for physics updates
      guard time - lastUpdateTime > 0.033 else { return }
      lastUpdateTime = time
      let vm = viewModel
      Task { @MainActor in
        vm.updateSimulation()
      }
    }
  }
}

// MARK: - View Model

@MainActor
class MemoryGraphViewModel: ObservableObject {
  @Published var isLoading = false
  @Published var isRebuilding = false
  @Published var isEmpty = true
  @Published var selectedNodeId: String?

  let scene = SCNScene()
  let cameraNode = SCNNode()

  private var simulation = ForceDirectedSimulation()
  private var nodeSceneNodes: [String: SCNNode] = [:]
  private var edgeSceneNodes: [String: SCNNode] = [:]
  private var isAnimating = true
  // Revisit guards: the VM is session-persistent (ViewModelContainer), so a
  // page visit renders the existing scene instantly. Non-forced loads are
  // TTL-throttled, single-flight, and skip the expensive re-simulation when
  // the fetched graph is unchanged.
  private var lastLoadedAt = Date.distantPast
  private var isPreparing = false
  private var hasRunEmptyBootstrap = false
  private var loadedGraphSignature: Int?
  private var sessionGeneration = 0

  init() {
    setupCamera()
    setupLighting()
  }

  private func setupCamera() {
    let camera = SCNCamera()
    camera.zNear = 1
    camera.zFar = 20000
    camera.fieldOfView = 60
    cameraNode.camera = camera
    cameraNode.position = SCNVector3(0, 0, 2000)  // Initial default, auto-adjusted after layout
    scene.rootNode.addChildNode(cameraNode)
  }

  private func setupLighting() {
    // Ambient light
    let ambientLight = SCNLight()
    ambientLight.type = .ambient
    ambientLight.intensity = 500
    ambientLight.color = NSColor.white
    let ambientNode = SCNNode()
    ambientNode.light = ambientLight
    scene.rootNode.addChildNode(ambientNode)

    // Directional light
    let directionalLight = SCNLight()
    directionalLight.type = .directional
    directionalLight.intensity = 800
    let directionalNode = SCNNode()
    directionalNode.light = directionalLight
    directionalNode.position = SCNVector3(0, 1000, 1000)
    directionalNode.look(at: SCNVector3(0, 0, 0))
    scene.rootNode.addChildNode(directionalNode)
  }

  // MARK: - Load Graph

  func prepareGraph() async {
    guard !isPreparing else { return }
    let generation = sessionGeneration
    isPreparing = true
    defer {
      if generation == sessionGeneration {
        isPreparing = false
      }
    }

    // A rendered scene within the cooldown is served as-is — visiting the
    // page must not refetch, re-run the force layout, or reset the camera.
    if !isEmpty,
      !PollingConfig.shouldAllowActivationRefresh(lastRefresh: lastLoadedAt)
    {
      return
    }

    await loadGraph(generation: generation)
    guard generation == sessionGeneration else { return }

    if isEmpty && !hasRunEmptyBootstrap {
      // First-session bootstrap for sparse accounts: ask the backend to build
      // the graph, then poll for it. Run once per session — not per visit.
      guard await rebuildGraph(generation: generation) else { return }
      hasRunEmptyBootstrap = true
      for _ in 1...10 {
        try? await Task.sleep(nanoseconds: 3_000_000_000)
        guard generation == sessionGeneration else { return }
        await loadGraph(generation: generation)
        if !isEmpty { break }
      }
    }
  }

  func loadGraph() async {
    await loadGraph(generation: sessionGeneration)
  }

  private func loadGraph(generation: Int) async {
    // Only surface the spinner while there's no scene to show — freshness
    // checks over a rendered graph stay invisible.
    let showSpinner = isEmpty
    if showSpinner { isLoading = true }
    defer {
      if showSpinner && generation == sessionGeneration {
        isLoading = false
      }
    }

    do {
      let response = try await fetchGraph()
      guard generation == sessionGeneration else { return }

      log("Knowledge graph: \(response.nodes.count) nodes, \(response.edges.count) edges")
      isEmpty = response.nodes.isEmpty
      lastLoadedAt = Date()

      guard !isEmpty else { return }

      // Same graph as last time → keep the settled scene. Re-simulating and
      // recreating scene nodes for identical data is what made every page
      // visit visibly "reload" the brain map.
      let signature = Self.graphSignature(of: response)
      if signature == loadedGraphSignature {
        return
      }
      loadedGraphSignature = signature

      // Populate simulation with user node at center
      let userName = AuthService.shared.displayName.isEmpty ? nil : AuthService.shared.givenName
      log("User name for center node: \(userName ?? "nil")")
      let populateStart = CFAbsoluteTimeGetCurrent()
      simulation.populate(graphResponse: response, userNodeLabel: userName)
      log(
        "Simulation populated: \(simulation.nodes.count) nodes (including user), \(simulation.edges.count) edges"
      )
      logPerf(
        "MemoryGraph: populate", duration: CFAbsoluteTimeGetCurrent() - populateStart)

      // A settled layout for this exact graph renders instantly — restore it
      // and skip both the physics run and the visual settle animation.
      let layoutStart = CFAbsoluteTimeGetCurrent()
      let restoredLayout =
        loadCachedLayout(signature: signature).map { simulation.applyLayout($0) } ?? false
      if !restoredLayout {
        // Suppress the render-driven simulation.tick() while the off-main physics
        // run mutates the same node positions/velocities. The SceneKit delegate
        // enqueues updateSimulation() on the main actor every frame; without this
        // it would tick() concurrently with runSync() off-main — an unsynchronized
        // read/write of non-atomic SIMD3 node state (torn positions, corrupt
        // layout/camera). The post-layout block below re-enables animation once the
        // detached run has completed.
        isAnimating = false
        // Run initial layout off main thread for responsiveness
        await Task.detached(priority: .userInitiated) { [simulation] in
          simulation.runSync(ticks: 800)
        }.value
        guard generation == sessionGeneration else { return }
        saveLayoutCache(signature: signature)
      }
      logPerf(
        "MemoryGraph: layout (restored=\(restoredLayout))",
        duration: CFAbsoluteTimeGetCurrent() - layoutStart)

      guard generation == sessionGeneration else { return }

      // Create scene nodes
      let sceneStart = CFAbsoluteTimeGetCurrent()
      createSceneNodes()
      logPerf("MemoryGraph: scene build", duration: CFAbsoluteTimeGetCurrent() - sceneStart)

      if restoredLayout {
        isAnimating = false
      } else {
        // Brief animation to settle, then stop
        isAnimating = true
        Task {
          try? await Task.sleep(nanoseconds: 3_000_000_000)  // 3s of live physics
          await MainActor.run { isAnimating = false }
        }
      }
    } catch {
      log("Failed to load knowledge graph: \(error.localizedDescription)")
    }
  }

  private struct GraphLayoutCache: Codable {
    let signature: Int
    let positions: [String: [Float]]
  }

  private static func layoutCacheURL() -> URL? {
    guard let userId = UserDefaults.standard.string(forKey: "auth_userId"), !userId.isEmpty
    else { return nil }

    let dir = DesktopLocalProfile.applicationSupportURL()
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(userId, isDirectory: true)

    do {
      try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
      return dir.appendingPathComponent("memory-graph-layout.json")
    } catch {
      logError("MemoryGraph: failed to prepare layout cache directory", error: error)
      return nil
    }
  }

  private func loadCachedLayout(signature: Int) -> [String: SIMD3<Float>]? {
    guard let url = Self.layoutCacheURL(), FileManager.default.fileExists(atPath: url.path)
    else { return nil }

    let cache: GraphLayoutCache
    do {
      let data = try Data(contentsOf: url)
      cache = try JSONDecoder().decode(GraphLayoutCache.self, from: data)
    } catch {
      logError("MemoryGraph: failed to read layout cache", error: error)
      return nil
    }

    guard cache.signature == signature else { return nil }
    var positions: [String: SIMD3<Float>] = [:]
    positions.reserveCapacity(cache.positions.count)
    for (id, values) in cache.positions where values.count == 3 {
      positions[id] = SIMD3<Float>(values[0], values[1], values[2])
    }
    return positions
  }

  private func saveLayoutCache(signature: Int) {
    guard let url = Self.layoutCacheURL() else { return }
    var positions: [String: [Float]] = [:]
    for (id, position) in simulation.layoutPositions() {
      positions[id] = [position.x, position.y, position.z]
    }
    let cache = GraphLayoutCache(signature: signature, positions: positions)
    do {
      let data = try JSONEncoder().encode(cache)
      try data.write(to: url, options: .atomic)
    } catch {
      logError("MemoryGraph: failed to write layout cache", error: error)
    }
  }

  /// Stable across launches — Swift's `Hasher` is per-process seeded, which
  /// would silently invalidate the on-disk layout cache on every restart.
  static func graphSignature(of response: KnowledgeGraphResponse) -> Int {
    var hash: UInt64 = 0xcbf2_9ce4_8422_2325  // FNV-1a
    func combine(_ string: String) {
      for byte in string.utf8 {
        hash ^= UInt64(byte)
        hash = hash &* 0x0000_0100_0000_01b3
      }
      hash ^= 0xff
      hash = hash &* 0x0000_0100_0000_01b3
    }
    combine(String(response.nodes.count))
    combine(String(response.edges.count))
    for node in response.nodes.sorted(by: { $0.id < $1.id }) {
      combine(node.id)
      combine(node.label)
      combine(node.nodeType.rawValue)
    }
    for edge in response.edges.sorted(by: { $0.id < $1.id }) {
      combine(edge.id)
      combine(edge.sourceId)
      combine(edge.targetId)
      combine(edge.label)
    }
    return Int(bitPattern: UInt(truncatingIfNeeded: hash))
  }

  private func fetchGraph() async throws -> KnowledgeGraphResponse {
    var response = await KnowledgeGraphStorage.shared.loadGraph()
    if !response.nodes.isEmpty {
      return response
    }

    for attempt in 0..<4 {
      if AuthState.shared.isRestoringAuth {
        try? await Task.sleep(nanoseconds: 500_000_000)
        continue
      }

      do {
        return try await APIClient.shared.getKnowledgeGraph()
      } catch {
        if case AuthError.notSignedIn = error,
          AuthState.shared.isSignedIn || AuthState.shared.isRestoringAuth,
          attempt < 3
        {
          try? await Task.sleep(nanoseconds: 1_000_000_000)
          continue
        }
        throw error
      }
    }

    response = await KnowledgeGraphStorage.shared.loadGraph()
    return response
  }

  // MARK: - Rebuild Graph

  @discardableResult
  func rebuildGraph() async -> Bool {
    await rebuildGraph(generation: sessionGeneration)
  }

  @discardableResult
  private func rebuildGraph(generation: Int) async -> Bool {
    isRebuilding = true
    defer {
      if generation == sessionGeneration {
        isRebuilding = false
      }
    }

    do {
      _ = try await APIClient.shared.rebuildKnowledgeGraph()

      // Wait a bit for the backend to process
      try await Task.sleep(nanoseconds: 2_000_000_000)
      guard generation == sessionGeneration else { return false }

      // Reload the graph
      await loadGraph(generation: generation)
      return true
    } catch {
      log("Failed to rebuild knowledge graph: \(error.localizedDescription)")
      return false
    }
  }

  // MARK: - Incremental Graph Update

  /// Add new graph data from storage incrementally (used during onboarding)
  func addGraphFromStorage() async {
    let generation = sessionGeneration
    let response = await KnowledgeGraphStorage.shared.loadGraph()
    guard generation == sessionGeneration else { return }
    guard !response.nodes.isEmpty else { return }
    isEmpty = false

    let userName = AuthService.shared.displayName.isEmpty ? nil : AuthService.shared.givenName
    simulation.addNodesAndEdges(graphResponse: response, userNodeLabel: userName)

    // Suppress the render-driven tick() while this off-main physics burst mutates
    // the (already-live) scene's node state — same main-vs-detached data race as
    // loadGraph. Re-enabled for the settle animation below, after the detached run.
    isAnimating = false

    // Run a burst of physics to integrate new nodes
    await Task.detached(priority: .userInitiated) { [simulation] in
      simulation.runSync(ticks: 200)
    }.value
    guard generation == sessionGeneration else { return }

    // Create scene nodes for new entries, animate them in
    addNewSceneNodes()
    autoFitCamera(animated: true)

    // Re-enable animation for settling
    isAnimating = true
    Task {
      try? await Task.sleep(nanoseconds: 3_000_000_000)
      await MainActor.run { isAnimating = false }
    }
  }

  func resetSessionState() {
    sessionGeneration += 1
    clearGraphScene()
    simulation = ForceDirectedSimulation()
    isLoading = false
    isRebuilding = false
    isEmpty = true
    selectedNodeId = nil
    isAnimating = false
    lastLoadedAt = .distantPast
    isPreparing = false
    hasRunEmptyBootstrap = false
    loadedGraphSignature = nil
    cameraNode.position = SCNVector3(0, 0, 2000)
  }

  private func clearGraphScene() {
    for (_, node) in nodeSceneNodes { node.removeFromParentNode() }
    for (_, node) in edgeSceneNodes { node.removeFromParentNode() }
    nodeSceneNodes.removeAll()
    edgeSceneNodes.removeAll()
  }

  /// Create scene nodes only for simulation nodes/edges not yet in the scene
  private func addNewSceneNodes() {
    let billboardConstraint = SCNBillboardConstraint()
    billboardConstraint.freeAxes = [.X, .Y]

    // Add new edges
    for edge in simulation.edges {
      guard edgeSceneNodes[edge.id] == nil else { continue }
      guard let source = simulation.nodeMap[edge.sourceId],
        let target = simulation.nodeMap[edge.targetId]
      else { continue }

      let edgeColor = blendColors(source.nodeType.nsColor, target.nodeType.nsColor, alpha: 0.25)
      let edgeMaterial = SCNMaterial()
      edgeMaterial.diffuse.contents = edgeColor
      edgeMaterial.emission.contents = edgeColor.withAlphaComponent(0.15)
      edgeMaterial.lightingModel = .constant

      let edgeNode = createEdgeNode(
        from: source.position, to: target.position, material: edgeMaterial)
      edgeNode.name = edge.id
      edgeNode.opacity = 0
      scene.rootNode.addChildNode(edgeNode)
      edgeSceneNodes[edge.id] = edgeNode

      // Fade in
      SCNTransaction.begin()
      SCNTransaction.animationDuration = 0.5
      edgeNode.opacity = 1
      SCNTransaction.commit()
    }

    // Add new node spheres
    for node in simulation.nodes {
      guard nodeSceneNodes[node.id] == nil else { continue }

      let radius = nodeRadius(for: node)
      let containerNode = SCNNode()
      containerNode.position = SCNVector3(node.position)
      containerNode.name = node.id
      containerNode.scale = SCNVector3(0.01, 0.01, 0.01)  // Start tiny for scale-in

      // Core sphere
      let sphere = SCNSphere(radius: radius)
      sphere.segmentCount = node.isFixed ? 24 : 16
      let mat = SCNMaterial()
      if node.isFixed {
        mat.diffuse.contents = NSColor.white
        mat.emission.contents = NSColor.white.withAlphaComponent(0.8)
      } else {
        mat.diffuse.contents = node.nodeType.nsColor
        mat.emission.contents = node.nodeType.nsColor.withAlphaComponent(0.5)
      }
      mat.lightingModel = .constant
      sphere.materials = [mat]
      let sphereNode = SCNNode(geometry: sphere)
      containerNode.addChildNode(sphereNode)

      // Glow halo
      let glowRadius = radius * 2.5
      let glowSphere = SCNSphere(radius: glowRadius)
      glowSphere.segmentCount = 48
      let glowMat = SCNMaterial()
      let glowColor = node.isFixed ? NSColor.white : node.nodeType.nsColor
      glowMat.diffuse.contents = glowColor.withAlphaComponent(0.03)
      glowMat.emission.contents = glowColor.withAlphaComponent(0.025)
      glowMat.lightingModel = .constant
      glowMat.isDoubleSided = true
      glowMat.blendMode = .add
      glowSphere.materials = [glowMat]
      let glowNode = SCNNode(geometry: glowSphere)
      containerNode.addChildNode(glowNode)

      // Text label
      let labelNode = createLabelNode(text: node.label, nodeRadius: radius, isFixed: node.isFixed)
      labelNode.constraints = [billboardConstraint]
      containerNode.addChildNode(labelNode)

      scene.rootNode.addChildNode(containerNode)
      nodeSceneNodes[node.id] = containerNode

      // Scale in from 0 with animation
      SCNTransaction.begin()
      SCNTransaction.animationDuration = 0.5
      containerNode.scale = SCNVector3(1, 1, 1)
      SCNTransaction.commit()
    }
  }

  // MARK: - Scene Nodes

  /// Compute node radius based on connection count (more connections = bigger)
  private func nodeRadius(for node: GraphNode3D) -> CGFloat {
    if node.isFixed { return 35 }  // User node is largest
    let base: CGFloat = 14
    let connectionBonus = CGFloat(min(node.connectionCount, 10)) * 2.5
    return base + connectionBonus
  }

  private func createSceneNodes() {
    // Clear existing nodes
    clearGraphScene()

    // Billboard constraint for labels (always face camera)
    let billboardConstraint = SCNBillboardConstraint()
    billboardConstraint.freeAxes = [.X, .Y]

    // Shared materials/geometry: nodes of the same type (and edges of the
    // same type pair) are visually identical, so building one material per
    // node/edge (~1,200 unique GPU objects for a mid-size graph) wasted both
    // build time and draw-call batching. Cache by visual identity instead.
    var edgeMaterialCache: [String: SCNMaterial] = [:]
    var bodyMaterialCache: [String: SCNMaterial] = [:]
    var glowMaterialCache: [String: SCNMaterial] = [:]
    var sphereCache: [String: SCNSphere] = [:]

    // Create edges first (behind nodes)
    for edge in simulation.edges {
      guard let source = simulation.nodeMap[edge.sourceId],
        let target = simulation.nodeMap[edge.targetId]
      else { continue }

      let edgeKey = "\(source.nodeType.rawValue)|\(target.nodeType.rawValue)"
      let edgeMaterial: SCNMaterial
      if let cached = edgeMaterialCache[edgeKey] {
        edgeMaterial = cached
      } else {
        let edgeColor = blendColors(
          source.nodeType.nsColor, target.nodeType.nsColor, alpha: 0.25)
        let material = SCNMaterial()
        material.diffuse.contents = edgeColor
        material.emission.contents = edgeColor.withAlphaComponent(0.15)
        material.lightingModel = .constant
        edgeMaterialCache[edgeKey] = material
        edgeMaterial = material
      }

      let edgeNode = createEdgeNode(
        from: source.position, to: target.position, material: edgeMaterial)
      edgeNode.name = edge.id
      scene.rootNode.addChildNode(edgeNode)
      edgeSceneNodes[edge.id] = edgeNode
    }

    // Create node spheres with labels and glow halos
    for node in simulation.nodes {
      let radius = nodeRadius(for: node)
      let containerNode = SCNNode()
      containerNode.position = SCNVector3(node.position)
      containerNode.name = node.id

      let materialKey = node.isFixed ? "fixed" : node.nodeType.rawValue

      // Core sphere
      let bodyMaterial: SCNMaterial
      if let cached = bodyMaterialCache[materialKey] {
        bodyMaterial = cached
      } else {
        let material = SCNMaterial()
        if node.isFixed {
          material.diffuse.contents = NSColor.white
          material.emission.contents = NSColor.white.withAlphaComponent(0.8)
        } else {
          material.diffuse.contents = node.nodeType.nsColor
          material.emission.contents = node.nodeType.nsColor.withAlphaComponent(0.5)
        }
        material.lightingModel = .constant
        bodyMaterialCache[materialKey] = material
        bodyMaterial = material
      }
      let segments = node.isFixed ? 24 : 16
      let sphereKey = "\(materialKey)|\(Int(radius * 10))|\(segments)"
      let sphere: SCNSphere
      if let cached = sphereCache[sphereKey] {
        sphere = cached
      } else {
        let newSphere = SCNSphere(radius: radius)
        newSphere.segmentCount = segments
        newSphere.materials = [bodyMaterial]
        sphereCache[sphereKey] = newSphere
        sphere = newSphere
      }
      let sphereNode = SCNNode(geometry: sphere)
      containerNode.addChildNode(sphereNode)

      // Glow halo (larger semi-transparent sphere around node). The halo is
      // an additive blur — 24 segments is visually identical to 48 at half
      // the tessellation.
      let glowRadius = radius * 2.5
      let glowMaterial: SCNMaterial
      if let cached = glowMaterialCache[materialKey] {
        glowMaterial = cached
      } else {
        let material = SCNMaterial()
        let glowColor = node.isFixed ? NSColor.white : node.nodeType.nsColor
        material.diffuse.contents = glowColor.withAlphaComponent(0.03)
        material.emission.contents = glowColor.withAlphaComponent(0.025)
        material.lightingModel = .constant
        material.isDoubleSided = true
        material.blendMode = .add
        glowMaterialCache[materialKey] = material
        glowMaterial = material
      }
      let glowKey = "glow|\(materialKey)|\(Int(glowRadius * 10))"
      let glowSphere: SCNSphere
      if let cached = sphereCache[glowKey] {
        glowSphere = cached
      } else {
        let newSphere = SCNSphere(radius: glowRadius)
        newSphere.segmentCount = 24
        newSphere.materials = [glowMaterial]
        sphereCache[glowKey] = newSphere
        glowSphere = newSphere
      }
      let glowNode = SCNNode(geometry: glowSphere)
      containerNode.addChildNode(glowNode)

      // Text label (billboard — always faces camera)
      let labelNode = createLabelNode(text: node.label, nodeRadius: radius, isFixed: node.isFixed)
      labelNode.constraints = [billboardConstraint]
      containerNode.addChildNode(labelNode)

      scene.rootNode.addChildNode(containerNode)
      nodeSceneNodes[node.id] = containerNode
    }

    // Auto-fit camera to graph bounds
    autoFitCamera()
  }

  /// Create a text label below a node
  private func createLabelNode(text: String, nodeRadius: CGFloat, isFixed: Bool) -> SCNNode {
    let truncated = text.count > 18 ? String(text.prefix(16)) + "..." : text
    let fontSize: CGFloat = isFixed ? 22 : 16
    let scnText = SCNText(string: truncated, extrusionDepth: 0)
    scnText.font = NSFont.systemFont(ofSize: fontSize, weight: isFixed ? .bold : .medium)
    scnText.flatness = 0.6
    scnText.alignmentMode = CATextLayerAlignmentMode.center.rawValue

    let textMat = SCNMaterial()
    textMat.diffuse.contents = NSColor.white
    textMat.emission.contents = NSColor.white.withAlphaComponent(0.9)
    textMat.lightingModel = .constant
    scnText.materials = [textMat]

    let textNode = SCNNode(geometry: scnText)

    // Center the text horizontally
    let (min, max) = scnText.boundingBox
    let textWidth = CGFloat(max.x - min.x)
    let textHeight = CGFloat(max.y - min.y)
    textNode.position = SCNVector3(
      -textWidth / 2,
      -(nodeRadius + textHeight + 12),
      0
    )

    // Scale text down to world-appropriate size
    let scale: Float = isFixed ? 1.2 : 0.9
    textNode.scale = SCNVector3(scale, scale, scale)

    return textNode
  }

  /// Blend two NSColors
  private func blendColors(_ a: NSColor, _ b: NSColor, alpha: CGFloat) -> NSColor {
    let aRGB = a.usingColorSpace(.sRGB) ?? a
    let bRGB = b.usingColorSpace(.sRGB) ?? b
    return NSColor(
      red: (aRGB.redComponent + bRGB.redComponent) / 2,
      green: (aRGB.greenComponent + bRGB.greenComponent) / 2,
      blue: (aRGB.blueComponent + bRGB.blueComponent) / 2,
      alpha: alpha
    )
  }

  /// Auto-fit camera distance to contain all nodes
  private func autoFitCamera(animated: Bool = false) {
    guard !simulation.nodes.isEmpty else { return }

    var maxDist: Float = 0
    for node in simulation.nodes {
      let dist = simd_length(node.position)
      if dist > maxDist { maxDist = dist }
    }

    // Camera needs to be far enough to see the outermost node
    // Account for field of view (60deg) — distance = maxDist / tan(fov/2) + padding
    let fovRadians: Float = 60.0 * Float.pi / 180.0
    let minDistance = maxDist / tan(fovRadians / 2) * 1.3  // 30% padding
    let cameraZ = max(minDistance, 1200)  // minimum distance for very small graphs

    if animated {
      SCNTransaction.begin()
      SCNTransaction.animationDuration = 0.8
      cameraNode.position = SCNVector3(0, 0, cameraZ)
      SCNTransaction.commit()
    } else {
      cameraNode.position = SCNVector3(0, 0, cameraZ)
    }
  }

  private func createEdgeNode(from: SIMD3<Float>, to: SIMD3<Float>, material: SCNMaterial)
    -> SCNNode
  {
    let fromVec = SCNVector3(from)
    let toVec = SCNVector3(to)

    let distance = sqrt(
      pow(toVec.x - fromVec.x, 2) + pow(toVec.y - fromVec.y, 2) + pow(toVec.z - fromVec.z, 2)
    )

    let cylinder = SCNCylinder(radius: 0.8, height: CGFloat(distance))
    cylinder.radialSegmentCount = 6
    cylinder.materials = [material]

    let node = SCNNode(geometry: cylinder)
    node.position = SCNVector3(
      (fromVec.x + toVec.x) / 2,
      (fromVec.y + toVec.y) / 2,
      (fromVec.z + toVec.z) / 2
    )
    node.look(at: toVec, up: SCNVector3(0, 1, 0), localFront: SCNVector3(0, 1, 0))

    return node
  }

  // MARK: - Animation

  func updateSimulation() {
    guard isAnimating, !simulation.isStable else { return }

    simulation.tick()

    // Batch all position updates without animation
    SCNTransaction.begin()
    SCNTransaction.disableActions = true

    for node in simulation.nodes {
      nodeSceneNodes[node.id]?.position = SCNVector3(node.position)
    }

    for edge in simulation.edges {
      guard let source = simulation.nodeMap[edge.sourceId],
        let target = simulation.nodeMap[edge.targetId],
        let edgeNode = edgeSceneNodes[edge.id]
      else { continue }
      updateEdgeNode(edgeNode, from: source.position, to: target.position)
    }

    SCNTransaction.commit()
  }

  private func updateEdgeNode(_ node: SCNNode, from: SIMD3<Float>, to: SIMD3<Float>) {
    let fromVec = SCNVector3(from)
    let toVec = SCNVector3(to)

    let dx = toVec.x - fromVec.x
    let dy = toVec.y - fromVec.y
    let dz = toVec.z - fromVec.z
    let distance = sqrt(dx * dx + dy * dy + dz * dz)

    if let cylinder = node.geometry as? SCNCylinder {
      cylinder.height = CGFloat(distance)
    }
    node.position = SCNVector3(
      (fromVec.x + toVec.x) / 2,
      (fromVec.y + toVec.y) / 2,
      (fromVec.z + toVec.z) / 2
    )
    node.look(at: toVec, up: SCNVector3(0, 1, 0), localFront: SCNVector3(0, 1, 0))
  }

  // MARK: - Share

  func shareGraph() {
    // TODO: Implement screenshot and share
    log("Share graph - not yet implemented")
  }
}

// MARK: - Extensions

extension KnowledgeGraphNodeType: CaseIterable {
  static var allCases: [KnowledgeGraphNodeType] {
    [.person, .place, .organization, .thing, .concept]
  }

  var displayName: String {
    switch self {
    case .person: return "Person"
    case .place: return "Place"
    case .organization: return "Organization"
    case .thing: return "Thing"
    case .concept: return "Concept"
    }
  }

  var color: Color {
    switch self {
    case .person: return .cyan
    case .place: return Color(red: 0, green: 1, blue: 0.62)  // Mint
    case .organization: return .orange
    case .thing: return .yellow
    case .concept: return .blue
    }
  }

  var nsColor: NSColor {
    switch self {
    case .person: return .cyan
    case .place: return NSColor(red: 0, green: 1, blue: 0.62, alpha: 1)
    case .organization: return .orange
    case .thing: return .systemYellow
    case .concept: return .systemBlue
    }
  }
}

extension SCNVector3 {
  init(_ simd: SIMD3<Float>) {
    self.init(x: CGFloat(simd.x), y: CGFloat(simd.y), z: CGFloat(simd.z))
  }
}

// MARK: - Preview

#if canImport(PreviewsMacros)
  #Preview {
    MemoryGraphPage(viewModel: MemoryGraphViewModel())
      .frame(width: 800, height: 600)
  }
#endif
