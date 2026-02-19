import SwiftUI
import SceneKit

// MARK: - Memory Graph Page

struct MemoryGraphPage: View {
    @StateObject private var viewModel = MemoryGraphViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            // Full-bleed background + 3D scene
            OmiColors.backgroundSecondary.ignoresSafeArea()

            if !viewModel.isEmpty {
                MemoryGraphSceneView(viewModel: viewModel)
                    .ignoresSafeArea()
            }

            // Minimal floating controls — no boxes, no backgrounds
            VStack {
                HStack {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .scaledFont(size: 13, weight: .semibold)
                            .foregroundColor(.white.opacity(0.5))
                            .frame(width: 28, height: 28)
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    if viewModel.isRebuilding {
                        ProgressView()
                            .scaleEffect(0.6)
                            .tint(.white.opacity(0.5))
                    } else {
                        Button {
                            Task { await viewModel.rebuildGraph() }
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .scaledFont(size: 13)
                                .foregroundColor(.white.opacity(0.5))
                                .frame(width: 28, height: 28)
                        }
                        .buttonStyle(.plain)
                        .help("Rebuild graph")
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)

                Spacer()
            }

            // Loading / empty state — centered spinner, no extra chrome
            if viewModel.isLoading || (viewModel.isEmpty && !viewModel.isRebuilding) {
                ProgressView()
                    .scaleEffect(1.2)
                    .tint(.white.opacity(0.4))
            }
        }
        .task {
            await viewModel.loadGraph()
            if viewModel.isEmpty {
                await viewModel.rebuildGraph()
                for _ in 1...10 {
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                    await viewModel.loadGraph()
                    if !viewModel.isEmpty { break }
                }
            }
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
        scnView.autoenablesDefaultLighting = false // We set up our own lights
        scnView.backgroundColor = NSColor(red: 0x1A/255.0, green: 0x1A/255.0, blue: 0x1A/255.0, alpha: 1.0) // Match OmiColors.backgroundSecondary
        scnView.antialiasingMode = .multisampling2X // Lighter AA
        scnView.preferredFramesPerSecond = 30 // Cap render rate

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
            Task { @MainActor in
                viewModel.updateSimulation()
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
        cameraNode.position = SCNVector3(0, 0, 2000)
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

    func loadGraph() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let response = try await APIClient.shared.getKnowledgeGraph()
            log("Knowledge graph: \(response.nodes.count) nodes, \(response.edges.count) edges")
            isEmpty = response.nodes.isEmpty

            guard !isEmpty else { return }

            // Populate simulation with user node at center
            let userName = AuthService.shared.displayName.isEmpty ? nil : AuthService.shared.givenName
            log("User name for center node: \(userName ?? "nil")")
            simulation.populate(graphResponse: response, userNodeLabel: userName)
            log("Simulation populated: \(simulation.nodes.count) nodes (including user), \(simulation.edges.count) edges")

            // Run initial layout off main thread for responsiveness
            await Task.detached(priority: .userInitiated) { [simulation] in
                simulation.runSync(ticks: 800)
            }.value

            // Create scene nodes
            createSceneNodes()

            // Brief animation to settle, then stop
            isAnimating = true
            Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000) // 3s of live physics
                await MainActor.run { isAnimating = false }
            }
        } catch {
            log("Failed to load knowledge graph: \(error.localizedDescription)")
        }
    }

    // MARK: - Rebuild Graph

    func rebuildGraph() async {
        isRebuilding = true
        defer { isRebuilding = false }

        do {
            _ = try await APIClient.shared.rebuildKnowledgeGraph()

            // Wait a bit for the backend to process
            try await Task.sleep(nanoseconds: 2_000_000_000)

            // Reload the graph
            await loadGraph()
        } catch {
            log("Failed to rebuild knowledge graph: \(error.localizedDescription)")
        }
    }

    // MARK: - Scene Nodes

    // Pre-built shared geometries for each node type (avoids per-node geometry allocation)
    private var sharedSphereGeometries: [KnowledgeGraphNodeType: SCNSphere] = [:]

    private func getSharedSphere(for nodeType: KnowledgeGraphNodeType) -> SCNSphere {
        if let existing = sharedSphereGeometries[nodeType] {
            return existing
        }
        let sphere = SCNSphere(radius: 18)
        sphere.segmentCount = 12
        let material = SCNMaterial()
        material.diffuse.contents = nodeType.nsColor
        material.emission.contents = nodeType.nsColor.withAlphaComponent(0.4)
        material.lightingModel = .constant // Skip lighting calculations
        sphere.materials = [material]
        sharedSphereGeometries[nodeType] = sphere
        return sphere
    }

    private func createSceneNodes() {
        // Clear existing nodes
        for (_, node) in nodeSceneNodes { node.removeFromParentNode() }
        for (_, node) in edgeSceneNodes { node.removeFromParentNode() }
        nodeSceneNodes.removeAll()
        edgeSceneNodes.removeAll()
        sharedSphereGeometries.removeAll()

        // Shared edge material
        let edgeMaterial = SCNMaterial()
        edgeMaterial.diffuse.contents = NSColor.white.withAlphaComponent(0.15)
        edgeMaterial.lightingModel = .constant

        // Create edges first (behind nodes)
        for edge in simulation.edges {
            guard let source = simulation.nodeMap[edge.sourceId],
                  let target = simulation.nodeMap[edge.targetId] else { continue }

            let edgeNode = createEdgeNode(from: source.position, to: target.position, material: edgeMaterial)
            edgeNode.name = edge.id
            scene.rootNode.addChildNode(edgeNode)
            edgeSceneNodes[edge.id] = edgeNode
        }

        // Create node spheres (shared geometry per type, larger for fixed/user node)
        for node in simulation.nodes {
            let scnNode: SCNNode
            if node.isFixed {
                // User node — larger and white
                let userSphere = SCNSphere(radius: 30)
                userSphere.segmentCount = 16
                let mat = SCNMaterial()
                mat.diffuse.contents = NSColor.white
                mat.emission.contents = NSColor.white.withAlphaComponent(0.6)
                mat.lightingModel = .constant
                userSphere.materials = [mat]
                scnNode = SCNNode(geometry: userSphere)
            } else {
                let sphere = getSharedSphere(for: node.nodeType)
                scnNode = SCNNode(geometry: sphere)
            }
            scnNode.position = SCNVector3(node.position)
            scnNode.name = node.id

            scene.rootNode.addChildNode(scnNode)
            nodeSceneNodes[node.id] = scnNode
        }
    }

    private func createEdgeNode(from: SIMD3<Float>, to: SIMD3<Float>, material: SCNMaterial) -> SCNNode {
        let fromVec = SCNVector3(from)
        let toVec = SCNVector3(to)

        let distance = sqrt(
            pow(toVec.x - fromVec.x, 2) +
            pow(toVec.y - fromVec.y, 2) +
            pow(toVec.z - fromVec.z, 2)
        )

        let cylinder = SCNCylinder(radius: 0.5, height: CGFloat(distance))
        cylinder.radialSegmentCount = 4
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
                  let edgeNode = edgeSceneNodes[edge.id] else { continue }
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
        case .place: return Color(red: 0, green: 1, blue: 0.62) // Mint
        case .organization: return .orange
        case .thing: return .purple
        case .concept: return .blue
        }
    }

    var nsColor: NSColor {
        switch self {
        case .person: return .cyan
        case .place: return NSColor(red: 0, green: 1, blue: 0.62, alpha: 1)
        case .organization: return .orange
        case .thing: return .purple
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

#Preview {
    MemoryGraphPage()
        .frame(width: 800, height: 600)
}
