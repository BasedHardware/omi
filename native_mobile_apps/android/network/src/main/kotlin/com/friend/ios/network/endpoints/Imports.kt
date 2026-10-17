package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.ImportJob
import com.friend.ios.core.models.KnowledgeGraph
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.await
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Port of `APIClient+Imports.swift` (backend `routers/imports.py`). */
interface ImportsAPI {
    /** `POST v1/import/limitless?language=` with the zip as multipart field `file` (at most 100 MB). */
    suspend fun importLimitless(zip: ByteArray, filename: String, language: String): ImportJob
    /** `GET v1/import/jobs?limit=`, newest first. */
    suspend fun importJobs(): List<ImportJob>
    /** `POST v1/import/jobs/{id}/cancel` (pending or processing only). */
    suspend fun cancelImportJob(id: String)
    /** `DELETE v1/import/jobs/{id}`: the entry only, not its conversations (finished jobs only). */
    suspend fun deleteImportJob(id: String)
}

/** Port of `knowledgeGraph()` (`APIClient+MemoryExtras.swift`). */
interface KnowledgeGraphAPI {
    /** `GET v1/knowledge-graph` (slow on the server: a 60 s timeout). */
    suspend fun knowledgeGraph(): KnowledgeGraph
}

internal class ImportsEndpoints(private val http: HttpCore) : ImportsAPI, KnowledgeGraphAPI {
    override suspend fun importLimitless(zip: ByteArray, filename: String, language: String): ImportJob {
        val request = http.request(Method.POST, "v1/import/limitless", query = listOf("language" to language), body = Body.File("file", filename, "application/zip", zip))
        val text = call(request, 300)
        return ImportJobMapper.map(JsonAccess.obj(text)) ?: throw APIError.Decoding("ImportJobResponse")
    }

    override suspend fun importJobs(): List<ImportJob> =
        JsonAccess.array(http.data(Method.GET, "v1/import/jobs", query = listOf("limit" to "50"))).mapNotNull { (it as? JsonObject)?.let(ImportJobMapper::map) }

    override suspend fun cancelImportJob(id: String) {
        http.data(Method.POST, "v1/import/jobs/$id/cancel")
    }

    override suspend fun deleteImportJob(id: String) {
        http.data(Method.DELETE, "v1/import/jobs/$id")
    }

    override suspend fun knowledgeGraph(): KnowledgeGraph = KnowledgeGraphMapper.map(JsonAccess.obj(call(http.request(Method.GET, "v1/knowledge-graph"), 60)))

    /** One call with its own timeout (uploads and the graph take longer than the default 30 s). */
    private suspend fun call(request: okhttp3.Request, seconds: Long): String {
        val client = http.client.newBuilder().callTimeout(seconds, TimeUnit.SECONDS).readTimeout(seconds, TimeUnit.SECONDS).writeTimeout(seconds, TimeUnit.SECONDS).build()
        val response = try {
            client.newCall(request).await()
        } catch (e: IOException) {
            throw APIError.Transport(e.message ?: e.toString())
        }
        return response.use {
            val text = withContext(Dispatchers.IO) { it.body?.string().orEmpty() }
            if (it.code !in 200..299) throw APIError.Http(it.code, text.take(500))
            text
        }
    }
}

internal object ImportJobMapper {
    fun map(json: JsonObject): ImportJob? {
        val id = json.string("job_id") ?: return null
        return ImportJob(
            id = id,
            status = ImportJob.Status.from(json.string("status")) ?: ImportJob.Status.Failed,
            totalFiles = json.int("total_files"), processedFiles = json.int("processed_files"),
            created = json.int("conversations_created"), skipped = json.int("conversations_skipped"),
            createdAt = BackendDate.parse(json.string("created_at")),
            error = json.string("error"),
        )
    }
}

internal object KnowledgeGraphMapper {
    fun map(json: JsonObject): KnowledgeGraph {
        val nodes = json.objects("nodes").mapNotNull { node ->
            val id = node.string("id") ?: return@mapNotNull null
            KnowledgeGraph.Node(id, node.string("label") ?: id, node.string("node_type") ?: "concept", node.strings("memory_ids"))
        }
        val known = nodes.map { it.id }.toSet()
        val seen = HashSet<String>()
        val edges = json.objects("edges").mapNotNull { edge ->
            val source = edge.string("source_id") ?: return@mapNotNull null
            val target = edge.string("target_id") ?: return@mapNotNull null
            if (source == target || source !in known || target !in known) return@mapNotNull null
            if (!seen.add(listOf(source, target).sorted().joinToString("|"))) return@mapNotNull null
            KnowledgeGraph.Edge(source, target, edge.string("label").orEmpty())
        }
        return KnowledgeGraph(nodes, edges)
    }
}
