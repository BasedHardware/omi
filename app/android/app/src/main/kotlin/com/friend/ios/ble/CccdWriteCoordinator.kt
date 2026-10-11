package com.friend.ios.ble

/** Called only on the GATT callback handler, including timer and queue callbacks. */
internal class CccdWriteCoordinator<G : Any, D : Any>(
    private val isConnected: (G) -> Boolean,
    private val ownsCommand: (Runnable) -> Boolean,
    private val scheduleTimeout: (Runnable) -> Unit,
    private val cancelTimeout: (Runnable) -> Unit,
    private val completeCommand: (Runnable) -> Unit,
    private val retireConnection: (G) -> Unit,
    private val onAcknowledged: (G) -> Unit = {},
) {
    class Write<G, D>(
        val gatt: G,
        val descriptor: D,
        val command: Runnable,
        val completion: (Result<Unit>) -> Unit,
    ) {
        var timeout: Runnable? = null
    }

    private val writes = mutableSetOf<Write<G, D>>()
    private var active: Write<G, D>? = null

    fun tracksCommand(command: Runnable?): Boolean = writes.any { it.command === command }

    fun register(gatt: G, descriptor: D, command: Runnable,
                 completion: (Result<Unit>) -> Unit): Write<G, D> {
        return Write(gatt, descriptor, command, completion).also { writes.add(it) }
    }

    fun start(write: Write<G, D>, issueWrite: () -> Boolean) {
        if (write !in writes) return
        if (!isConnected(write.gatt) || !ownsCommand(write.command)) {
            settle(write, Result.failure(IllegalStateException("CCCD connection or command retired")))
            return
        }
        active = write
        // Claim and arm before issuing: even an immediate ACK cancels this exact timer.
        val timeout = Runnable { onTimeout(write) }
        write.timeout = timeout
        scheduleTimeout(timeout)
        try {
            if (!issueWrite()) {
                settle(write, Result.failure(IllegalStateException("CCCD write rejected")))
            }
        } catch (e: Exception) {
            settle(write, Result.failure(e))
        }
    }

    fun onDescriptorWrite(gatt: G, descriptor: D, result: Result<Unit>) {
        val write = active ?: return
        if (write.gatt !== gatt || write.descriptor !== descriptor ||
            !isConnected(gatt) || !ownsCommand(write.command)) return
        if (result.isSuccess) onAcknowledged(gatt)
        settle(write, result)
    }

    private fun onTimeout(write: Write<G, D>) {
        if (active !== write || write !in writes || !ownsCommand(write.command)) return
        active = null
        // Android ACKs have no write id. Do not run another write on this GATT.
        // Retirement clears its queue before completing any waiting Pigeon replies.
        retireConnection(write.gatt)
        failConnection(write.gatt, IllegalStateException("CCCD write timed out"))
    }

    private fun settle(write: Write<G, D>, result: Result<Unit>) {
        if (!writes.remove(write)) return
        if (active === write) active = null
        write.timeout?.let(cancelTimeout)
        write.timeout = null
        write.completion(result)
        if (ownsCommand(write.command)) completeCommand(write.command)
    }

    fun failConnection(gatt: G, error: Exception) {
        fail(writes.filter { it.gatt === gatt }, error)
    }

    fun failAll(error: Exception) {
        fail(writes.toList(), error)
    }

    private fun fail(pending: List<Write<G, D>>, error: Exception) {
        for (write in pending) {
            writes.remove(write)
            if (active === write) active = null
            write.timeout?.let(cancelTimeout)
            write.timeout = null
        }
        for (write in pending) write.completion(Result.failure(error))
    }
}
