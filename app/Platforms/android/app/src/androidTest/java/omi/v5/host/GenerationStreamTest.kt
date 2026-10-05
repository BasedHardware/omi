package omi.v5.host

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.net.ServerSocket
import java.util.Collections
import kotlin.concurrent.thread
import kotlinx.coroutines.runBlocking
import omi.kit.HTTPBackendTransport
import omi.kit.InMemoryCredentialStore
import omi.kit.StoredSession
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class GenerationStreamTest {
    @Test
    fun framesArriveBeforeTheStreamCloses() = runBlocking {
        val server = ServerSocket(0)
        val serverThread = thread {
            server.accept().use { socket ->
                val input = socket.getInputStream().bufferedReader()
                while (input.readLine()?.isNotEmpty() == true) {}
                val output = socket.getOutputStream()
                output.write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n".toByteArray())
                output.write("data: one\n\n".toByteArray())
                output.flush()
                Thread.sleep(1500)
                output.write("data: two\n\n".toByteArray())
                output.flush()
            }
        }

        val credentials = InMemoryCredentialStore()
        credentials.store(StoredSession(idToken = "synthetic-token", refreshToken = "synthetic-refresh"))
        val transport = HTTPBackendTransport(
            credentials = credentials,
            planeSelection = HTTPBackendTransport.PlaneSelection(storedPlane = "new", stampedValid = true),
            originOverride = "http://127.0.0.1:${server.localPort}",
        )

        val started = System.nanoTime()
        val arrivals = Collections.synchronizedList(mutableListOf<Pair<String, Long>>())
        val response = transport.generationEvents(generationId = "gen-1", lastEventId = null) { frame ->
            arrivals.add(frame to (System.nanoTime() - started) / 1_000_000)
        }
        val finished = (System.nanoTime() - started) / 1_000_000
        serverThread.join()
        server.close()

        assertEquals(200, response.status)
        assertEquals(listOf("data: one\n\n", "data: two\n\n"), arrivals.map { it.first })
        assertTrue("first frame at ${arrivals[0].second}ms, stream ended at ${finished}ms", arrivals[0].second < finished - 1000)
    }

    @Test
    fun redirectsAreNotFollowed() = runBlocking {
        val target = ServerSocket(0)
        val server = ServerSocket(0)
        var targetHit = false
        val targetThread = thread {
            try {
                target.soTimeout = 3000
                target.accept().use { targetHit = true }
            } catch (_: java.net.SocketTimeoutException) {
            }
        }
        val serverThread = thread {
            server.accept().use { socket ->
                val input = socket.getInputStream().bufferedReader()
                while (input.readLine()?.isNotEmpty() == true) {}
                socket.getOutputStream().write(
                    "HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:${target.localPort}/steal\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".toByteArray(),
                )
            }
        }

        val credentials = InMemoryCredentialStore()
        credentials.store(StoredSession(idToken = "synthetic-token", refreshToken = "synthetic-refresh"))
        val transport = HTTPBackendTransport(
            credentials = credentials,
            planeSelection = HTTPBackendTransport.PlaneSelection(storedPlane = "new", stampedValid = true),
            originOverride = "http://127.0.0.1:${server.localPort}",
        )

        val response = transport.generationEvents(generationId = "gen-2", lastEventId = null) { }
        serverThread.join()
        targetThread.join()
        server.close()
        target.close()

        assertEquals(302, response.status)
        assertTrue("redirect target was contacted", !targetHit)
    }
}
