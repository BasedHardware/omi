import SwiftUI
import SceneKit

// MARK: - Memory Graph Page

struct MemoryGraphPage: View {
    @StateObject private var viewModel = MemoryGraphViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            // Background
            Color.black.ignoresSafeArea()

            // 3D Scene
            if !viewModel.isEmpty {
                MemoryGraphSceneView(viewModel: viewModel)
                    .ignoresSafeArea()
            }

            // Overlay UI
            VStack {
                // Header
                headerView
                    .padding(.horizontal, 20)
                    .padding(.top, 12)

                Spacer()

                // Legend
                if !viewModel.isEmpty {
                    legendView
                        .padding(.horizontal, 20)
                        .padding(.bottom, 20)
                }
            }

            // Loading overlay
            if viewModel.isLoading {
                loadingOverlay
            }

            // Empty state
            if viewModel.isEmpty && !viewModel.isLoading {
                emptyStateView
            }

            // Rebuilding progress
            if viewModel.isRebuilding {
                rebuildingOverlay
            }
        }
        .task {
            await viewModel.loadGraph()
        }
    }

    // MARK: - Header

    private var headerView: some View {
        HStack {
            Button {
                dismiss()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 14, weight: .semibold))
                    Text("Back")
                        .font(.system(size: 14, weight: .medium))
                }
                .foregroundColor(.white.opacity(0.8))
            }
            .buttonStyle(.plain)

            Spacer()

            Text("Memory Graph")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)

            Spacer()

            HStack(spacing: 12) {
                // Rebuild button
                Button {
                    Task {
                        await viewModel.rebuildGraph()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 14))
                        .foregroundColor(.white.opacity(0.8))
                }
                .buttonStyle(.plain)
                .help("Rebuild graph from memories")
                .disabled(viewModel.isRebuilding)

                // Share button
                Button {
                    viewModel.shareGraph()
                } label: {
                    Image(systemName: "square.and.arrow.up")
                        .font(.system(size: 14))
                        .foregroundColor(.white.opacity(0.8))
                }
                .buttonStyle(.plain)
                .help("Share graph")
                .disabled(viewModel.isEmpty)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(.ultraThinMaterial.opacity(0.5))
        )
    }

    // MARK: - Legend

    private var legendView: some View {
        HStack(spacing: 16) {
            ForEach(KnowledgeGraphNodeType.allCases, id: \.self) { type in
                HStack(spacing: 6) {
                    Circle()
                        .fill(type.color)
                        .frame(width: 10, height: 10)
                    Text(type.displayName)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.white.opacity(0.7))
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(.ultraThinMaterial.opacity(0.5))
        )
    }

    // MARK: - Loading Overlay

    private var loadingOverlay: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
                .tint(.white)

            Text("Loading graph...")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.7))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black.opacity(0.5))
    }

    // MARK: - Rebuilding Overlay

    private var rebuildingOverlay: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
                .tint(.white)

            Text("Building knowledge graph...")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.7))

            Text("Extracting entities from your memories")
                .font(.system(size: 12))
                .foregroundColor(.white.opacity(0.5))
        }
        .padding(32)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(.ultraThinMaterial)
        )
    }

    // MARK: - Empty State

    private var emptyStateView: some View {
        VStack(spacing: 20) {
            Image(systemName: "brain")
                .font(.system(size: 64))
                .foregroundColor(.white.opacity(0.3))

            Text("No Knowledge Graph Yet")
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(.white)

            Text("Build your knowledge graph from your memories\nto see connections between people, places, and concepts.")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.6))
                .multilineTextAlignment(.center)
                .lineSpacing(4)

            Button {
                Task {
                    await viewModel.rebuildGraph()
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "sparkles")
                    Text("Build Graph")
                }
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.purple)
                )
            }
            .buttonStyle(.plain)
            .disabled(viewModel.isRebuilding)
        }
        .padding(40)
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
        scnView.autoenablesDefaultLighting = true
        scnView.backgroundColor = .black
        scnView.antialiasingMode = .multisampling4X

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

        init(viewModel: MemoryGraphViewModel) {
            self.viewModel = viewModel
        }

        func renderer(_ renderer: any SCNSceneRenderer, updateAtTime time: TimeInterval) {
            // Run physics simulation on main actor
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
        cameraNode.position = SCNVector3(0, 0, 4000)
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
            isEmpty = response.nodes.isEmpty

            guard !isEmpty else { return }

            // Populate simulation
            simulation.populate(graphResponse: response, userNodeLabel: nil)

            // Run initial layout
            simulation.runSync(ticks: 200)

            // Create scene nodes
            createSceneNodes()

            // Start animation
            isAnimating = true
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

    private func createSceneNodes() {
        // Clear existing nodes
        for (_, node) in nodeSceneNodes {
            node.removeFromParentNode()
        }
        for (_, node) in edgeSceneNodes {
            node.removeFromParentNode()
        }
        nodeSceneNodes.removeAll()
        edgeSceneNodes.removeAll()

        // Create node spheres
        for node in simulation.nodes {
            let sphere = SCNSphere(radius: 15)
            let material = SCNMaterial()
            material.diffuse.contents = node.nodeType.nsColor
            material.emission.contents = node.nodeType.nsColor.withAlphaComponent(0.3)
            sphere.materials = [material]

            let scnNode = SCNNode(geometry: sphere)
            scnNode.position = SCNVector3(node.position)
            scnNode.name = node.id

            // Add label
            let text = SCNText(string: node.label, extrusionDepth: 1)
            text.font = NSFont.systemFont(ofSize: 12, weight: .medium)
            text.flatness = 0.1
            let textMaterial = SCNMaterial()
            textMaterial.diffuse.contents = NSColor.white
            text.materials = [textMaterial]

            let textNode = SCNNode(geometry: text)
            textNode.scale = SCNVector3(1.5, 1.5, 1.5)

            // Center the text
            let (min, max) = text.boundingBox
            let dx = (max.x - min.x) / 2
            textNode.position = SCNVector3(-dx * 1.5, 25, 0)
            textNode.constraints = [SCNBillboardConstraint()]

            scnNode.addChildNode(textNode)
            scene.rootNode.addChildNode(scnNode)
            nodeSceneNodes[node.id] = scnNode
        }

        // Create edges
        for edge in simulation.edges {
            guard let source = simulation.nodeMap[edge.sourceId],
                  let target = simulation.nodeMap[edge.targetId] else { continue }

            let edgeNode = createEdgeNode(from: source.position, to: target.position)
            edgeNode.name = edge.id
            scene.rootNode.addChildNode(edgeNode)
            edgeSceneNodes[edge.id] = edgeNode
        }
    }

    private func createEdgeNode(from: SIMD3<Float>, to: SIMD3<Float>) -> SCNNode {
        let fromVec = SCNVector3(from)
        let toVec = SCNVector3(to)

        let distance = sqrt(
            pow(toVec.x - fromVec.x, 2) +
            pow(toVec.y - fromVec.y, 2) +
            pow(toVec.z - fromVec.z, 2)
        )

        let cylinder = SCNCylinder(radius: 1, height: CGFloat(distance))
        let material = SCNMaterial()
        material.diffuse.contents = NSColor.white.withAlphaComponent(0.3)
        cylinder.materials = [material]

        let node = SCNNode(geometry: cylinder)

        // Position at midpoint
        node.position = SCNVector3(
            (fromVec.x + toVec.x) / 2,
            (fromVec.y + toVec.y) / 2,
            (fromVec.z + toVec.z) / 2
        )

        // Rotate to align with direction
        node.look(at: toVec, up: SCNVector3(0, 1, 0), localFront: SCNVector3(0, 1, 0))

        return node
    }

    // MARK: - Animation

    func updateSimulation() {
        guard isAnimating, !simulation.isStable else { return }

        simulation.tick()

        // Update node positions
        for node in simulation.nodes {
            if let scnNode = nodeSceneNodes[node.id] {
                SCNTransaction.begin()
                SCNTransaction.animationDuration = 0.016
                scnNode.position = SCNVector3(node.position)
                SCNTransaction.commit()
            }
        }

        // Update edge positions
        for edge in simulation.edges {
            guard let source = simulation.nodeMap[edge.sourceId],
                  let target = simulation.nodeMap[edge.targetId],
                  let edgeNode = edgeSceneNodes[edge.id] else { continue }

            updateEdgeNode(edgeNode, from: source.position, to: target.position)
        }
    }

    private func updateEdgeNode(_ node: SCNNode, from: SIMD3<Float>, to: SIMD3<Float>) {
        let fromVec = SCNVector3(from)
        let toVec = SCNVector3(to)

        let distance = sqrt(
            pow(toVec.x - fromVec.x, 2) +
            pow(toVec.y - fromVec.y, 2) +
            pow(toVec.z - fromVec.z, 2)
        )

        // Update cylinder height
        if let cylinder = node.geometry as? SCNCylinder {
            cylinder.height = CGFloat(distance)
        }

        // Update position
        node.position = SCNVector3(
            (fromVec.x + toVec.x) / 2,
            (fromVec.y + toVec.y) / 2,
            (fromVec.z + toVec.z) / 2
        )

        // Update rotation
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
