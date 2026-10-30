package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.KnowledgeGraph
import com.friend.ios.network.APIClientProtocol
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Port of `KnowledgeGraphStore.swift`: the memory graph (Flutter `memory_graph_page`): people,
 * places and things Omi knows, linked to the user at the center. Laid out once per load with a
 * small force simulation.
 */
class KnowledgeGraphStore(private val api: APIClientProtocol, private val userName: String?) {
    enum class Phase { Idle, Loading, Loaded, Failed }

    data class PlacedNode(
        val node: KnowledgeGraph.Node,
        /** -1...1 on both axes; the user sits at (0, 0). */
        val x: Double,
        val y: Double,
        val isUser: Boolean,
    ) {
        val id: String get() = node.id
    }

    var phase: Phase by mutableStateOf(Phase.Idle)
        private set
    var nodes: List<PlacedNode> by mutableStateOf(emptyList())
        private set
    var edges: List<KnowledgeGraph.Edge> by mutableStateOf(emptyList())
        private set

    /** Nothing besides the user yet. */
    val isEmpty: Boolean get() = nodes.none { !it.isUser }

    /** Who is connected to [id], for highlighting a tapped node. */
    fun neighbors(id: String): Set<String> =
        edges.mapNotNull { if (it.source == id) it.target else if (it.target == id) it.source else null }.toSet()

    suspend fun load() {
        if (nodes.isEmpty()) phase = Phase.Loading
        try {
            val graph = GraphLayout.centered(userName, api.knowledgeGraph())
            val positions = withContext(Dispatchers.Default) { GraphLayout.positions(graph, GraphLayout.USER_ID) }
            nodes = graph.nodes.map { node ->
                val point = positions[node.id] ?: (0.0 to 0.0)
                PlacedNode(node, point.first, point.second, node.id == GraphLayout.USER_ID)
            }
            edges = graph.edges
            phase = Phase.Loaded
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            phase = Phase.Failed
        }
    }
}

/** Graph shaping and a deterministic 2D force layout (Flutter uses a 3D one; flat reads better here). */
object GraphLayout {
    const val USER_ID = "user-node"

    /**
     * Merges every node that stands for the user (type `user`, label "me" / "the user" / their
     * name) into one center node, adding it when missing, and repoints its edges.
     */
    fun centered(userName: String?, graph: KnowledgeGraph): KnowledgeGraph {
        val names = listOfNotNull("me", "the user", "user", userName?.lowercase()).toSet()
        val userNodes = graph.nodes.filter { it.kind == "user" || it.label.lowercase() in names }.map { it.id }.toSet()
        val label = graph.nodes.firstOrNull { it.id in userNodes && it.kind != "user" }?.label ?: userName ?: "You"
        val unique = HashSet<String>()
        val others = graph.nodes.filter { it.id !in userNodes && unique.add(it.id) }
        val seen = HashSet<String>()
        val edges = graph.edges.mapNotNull { edge ->
            val source = if (edge.source in userNodes) USER_ID else edge.source
            val target = if (edge.target in userNodes) USER_ID else edge.target
            if (source == target || !seen.add(listOf(source, target).sorted().joinToString("|"))) null
            else KnowledgeGraph.Edge(source, target, edge.label)
        }
        return KnowledgeGraph(listOf(KnowledgeGraph.Node(USER_ID, label, "user")) + others, edges)
    }

    /**
     * Positions in -1...1. Nodes start on a golden-angle spiral (stable across loads), then repel
     * each other while edges pull linked nodes together; [center] stays fixed at the origin.
     */
    fun positions(graph: KnowledgeGraph, center: String): Map<String, Pair<Double, Double>> {
        val ids = graph.nodes.map { it.id }
        val count = ids.size
        if (count <= 1) return ids.associateWith { 0.0 to 0.0 }
        val index = HashMap<String, Int>()
        ids.forEachIndexed { i, id -> index.putIfAbsent(id, i) }
        val links = graph.edges.mapNotNull { edge -> index[edge.source]?.let { s -> index[edge.target]?.let { s to it } } }
        val fixed = index[center]
        val x = DoubleArray(count)
        val y = DoubleArray(count)
        for (i in 0 until count) {
            if (i == fixed) continue
            val radius = 0.2 + 0.8 * sqrt(i.toDouble() / count)
            x[i] = radius * cos(i * 2.399963)
            y[i] = radius * sin(i * 2.399963)
        }
        val ideal = 1.2 / sqrt(count.toDouble())
        val steps = if (count > 150) 80 else 240
        for (step in 0 until steps) {
            val cooling = 0.08 * (1 - step.toDouble() / steps)
            val fx = DoubleArray(count)
            val fy = DoubleArray(count)
            for (a in 0 until count) {
                for (b in a + 1 until count) {
                    val dx = x[a] - x[b]
                    val dy = y[a] - y[b]
                    val distance = max(sqrt(dx * dx + dy * dy), 0.01)
                    val push = ideal * ideal / (distance * distance)
                    fx[a] += dx * push; fy[a] += dy * push
                    fx[b] -= dx * push; fy[b] -= dy * push
                }
            }
            for ((s, t) in links) {
                val dx = x[s] - x[t]
                val dy = y[s] - y[t]
                val pull = sqrt(dx * dx + dy * dy) / ideal
                fx[s] -= dx * pull; fy[s] -= dy * pull
                fx[t] += dx * pull; fy[t] += dy * pull
            }
            for (i in 0 until count) {
                if (i == fixed) continue
                val length = max(sqrt(fx[i] * fx[i] + fy[i] * fy[i]), 0.0001)
                val move = min(length, cooling)
                x[i] += fx[i] / length * move
                y[i] += fy[i] / length * move
            }
        }
        val extent = max((0 until count).maxOf { max(abs(x[it]), abs(y[it])) }, 0.001)
        val result = HashMap<String, Pair<Double, Double>>()
        ids.forEachIndexed { i, id -> result.putIfAbsent(id, x[i] / extent to y[i] / extent) }
        return result
    }
}
