import Foundation
import simd

// MARK: - 3D Graph Node for Physics

class GraphNode3D {
    let id: String
    let label: String
    let nodeType: KnowledgeGraphNodeType

    var position: SIMD3<Float>
    var velocity: SIMD3<Float> = .zero
    var force: SIMD3<Float> = .zero
    var isFixed: Bool = false
    var connectionCount: Int = 0

    init(id: String, label: String, nodeType: KnowledgeGraphNodeType) {
        self.id = id
        self.label = label
        self.nodeType = nodeType
        // Random initial position in a sphere
        let theta = Float.random(in: 0...(2 * .pi))
        let phi = Float.random(in: 0...Float.pi)
        let r = Float.random(in: 200...600)
        self.position = SIMD3<Float>(
            r * sin(phi) * cos(theta),
            r * sin(phi) * sin(theta),
            r * cos(phi)
        )
    }
}

// MARK: - 3D Graph Edge

struct GraphEdge3D {
    let id: String
    let sourceId: String
    let targetId: String
    let label: String
}

// MARK: - Force-Directed Layout Simulation

class ForceDirectedSimulation {
    var nodes: [GraphNode3D] = []
    var edges: [GraphEdge3D] = []
    var nodeMap: [String: GraphNode3D] = [:]

    // Physics parameters (adjusted dynamically in populate() based on graph size)
    var repulsion: Float = 80_000
    var attraction: Float = 0.003
    var centerGravity: Float = 0.0008
    let damping: Float = 0.9
    let dt: Float = 0.016
    var restLength: Float = 600
    let maxSpeed: Float = 40

    private var tickCount = 0
    private var stableFrameCount = 0
    private let stableThreshold: Float = 0.2
    private let stableFramesRequired = 10

    var isStable: Bool { stableFrameCount >= stableFramesRequired }

    /// Populate the simulation with nodes and edges from API response
    func populate(graphResponse: KnowledgeGraphResponse, userNodeLabel: String?) {
        nodes.removeAll()
        edges.removeAll()
        nodeMap.removeAll()

        // Pre-compute connection counts from API edges
        var connectionCounts: [String: Int] = [:]
        for edge in graphResponse.edges {
            connectionCounts[edge.sourceId, default: 0] += 1
            connectionCounts[edge.targetId, default: 0] += 1
        }

        // Create 3D nodes
        var foundUserNode = false
        for node in graphResponse.nodes {
            let node3D = GraphNode3D(
                id: node.id,
                label: node.label,
                nodeType: node.nodeType
            )
            node3D.connectionCount = connectionCounts[node.id] ?? 0

            // Fix the user node at center
            if let userName = userNodeLabel,
               node.label.lowercased() == userName.lowercased() {
                node3D.position = .zero
                node3D.isFixed = true
                foundUserNode = true
            }

            nodes.append(node3D)
            nodeMap[node.id] = node3D
        }

        // Always create a center "me" node if none was found
        if !foundUserNode {
            let meNode = GraphNode3D(
                id: "__user_center__",
                label: userNodeLabel ?? "Me",
                nodeType: .person
            )
            meNode.position = .zero
            meNode.isFixed = true
            nodes.insert(meNode, at: 0)
            nodeMap[meNode.id] = meNode

            // Connect "me" to the most-connected nodes
            let topNodes = connectionCounts.sorted { $0.value > $1.value }.prefix(min(8, graphResponse.nodes.count / 3 + 1))
            for (nodeId, _) in topNodes {
                edges.append(GraphEdge3D(
                    id: "__user_edge_\(nodeId)__",
                    sourceId: "__user_center__",
                    targetId: nodeId,
                    label: ""
                ))
                // Update connection counts for the user edges
                nodeMap[nodeId]?.connectionCount += 1
            }
            meNode.connectionCount = topNodes.count
        }

        // Create edges
        for edge in graphResponse.edges {
            edges.append(GraphEdge3D(
                id: edge.id,
                sourceId: edge.sourceId,
                targetId: edge.targetId,
                label: edge.label
            ))
        }

        // Adapt physics parameters to graph size
        let nodeCount = nodes.count
        if nodeCount <= 15 {
            // Small graph: tighter layout so it doesn't look sparse
            restLength = 300
            repulsion = 50_000
            centerGravity = 0.002
            attraction = 0.005
        } else if nodeCount <= 40 {
            // Medium graph
            restLength = 450
            repulsion = 65_000
            centerGravity = 0.001
            attraction = 0.004
        } else {
            // Large graph: spread out
            restLength = 600
            repulsion = 80_000
            centerGravity = 0.0008
            attraction = 0.003
        }

        // Reset simulation state
        tickCount = 0
        stableFrameCount = 0
    }

    /// Run one tick of the physics simulation
    func tick() {
        tickCount += 1

        // Only run physics every 2 ticks for smoother animation
        guard tickCount % 2 == 0 else { return }

        // 1. Reset forces
        for node in nodes {
            node.force = .zero
        }

        // 2. Calculate repulsive forces (Coulomb-like)
        let nodeCount = nodes.count
        for i in 0..<nodeCount {
            guard !nodes[i].isFixed else { continue }

            for j in (i + 1)..<nodeCount {
                let delta = nodes[j].position - nodes[i].position
                let distSq = max(simd_length_squared(delta), 100) // Avoid division by zero

                // Skip very distant pairs for performance
                guard distSq < 100_000_000 else { continue }

                let dist = sqrt(distSq)
                let direction = delta / dist
                let forceMagnitude = repulsion / distSq
                let force = direction * forceMagnitude

                nodes[i].force -= force
                if !nodes[j].isFixed {
                    nodes[j].force += force
                }
            }
        }

        // 3. Calculate attractive forces (spring-like along edges)
        for edge in edges {
            guard let source = nodeMap[edge.sourceId],
                  let target = nodeMap[edge.targetId] else { continue }

            let delta = target.position - source.position
            let dist = simd_length(delta)
            guard dist > 0 else { continue }

            let direction = delta / dist
            let displacement = dist - restLength
            let forceMagnitude = displacement * attraction
            let force = direction * forceMagnitude

            if !source.isFixed {
                source.force += force
            }
            if !target.isFixed {
                target.force -= force
            }
        }

        // 4. Apply center gravity
        for node in nodes where !node.isFixed {
            node.force -= node.position * centerGravity
        }

        // 5. Update velocities and positions
        var totalEnergy: Float = 0

        for node in nodes where !node.isFixed {
            // Update velocity
            node.velocity += node.force * dt
            node.velocity *= damping

            // Cap max speed
            let speed = simd_length(node.velocity)
            if speed > maxSpeed {
                node.velocity = simd_normalize(node.velocity) * maxSpeed
            }

            // Update position
            node.position += node.velocity

            // Accumulate kinetic energy
            totalEnergy += speed * speed
        }

        // 6. Check for stability
        if totalEnergy < stableThreshold {
            stableFrameCount += 1
        } else {
            stableFrameCount = 0
        }
    }

    /// Run multiple physics steps synchronously (for initial layout)
    /// Bypasses tick counting for full-speed computation.
    func runSync(ticks: Int) {
        for _ in 0..<ticks {
            runPhysicsStep()
        }
    }

    /// One full physics step (no tick-skipping)
    private func runPhysicsStep() {
        // 1. Reset forces
        for node in nodes {
            node.force = .zero
        }

        // 2. Calculate repulsive forces (Coulomb-like)
        let nodeCount = nodes.count
        for i in 0..<nodeCount {
            guard !nodes[i].isFixed else { continue }

            for j in (i + 1)..<nodeCount {
                let delta = nodes[j].position - nodes[i].position
                let distSq = max(simd_length_squared(delta), 100)

                guard distSq < 100_000_000 else { continue }

                let dist = sqrt(distSq)
                let direction = delta / dist
                let forceMagnitude = repulsion / distSq
                let force = direction * forceMagnitude

                nodes[i].force -= force
                if !nodes[j].isFixed {
                    nodes[j].force += force
                }
            }
        }

        // 3. Calculate attractive forces
        for edge in edges {
            guard let source = nodeMap[edge.sourceId],
                  let target = nodeMap[edge.targetId] else { continue }

            let delta = target.position - source.position
            let dist = simd_length(delta)
            guard dist > 0 else { continue }

            let direction = delta / dist
            let displacement = dist - restLength
            let forceMagnitude = displacement * attraction
            let force = direction * forceMagnitude

            if !source.isFixed { source.force += force }
            if !target.isFixed { target.force -= force }
        }

        // 4. Center gravity
        for node in nodes where !node.isFixed {
            node.force -= node.position * centerGravity
        }

        // 5. Update velocities and positions
        for node in nodes where !node.isFixed {
            node.velocity += node.force * dt
            node.velocity *= damping

            let speed = simd_length(node.velocity)
            if speed > maxSpeed {
                node.velocity = simd_normalize(node.velocity) * maxSpeed
            }
            node.position += node.velocity
        }
    }

    /// Wake up the simulation (reset stability counter)
    func wake() {
        stableFrameCount = 0
    }
}
