package com.friend.ios.ble

/** Serial GATT work, fenced by the connection instance and callback identity. */
internal class GattCommandQueue<O : Any>(
    private val post: (() -> Unit) -> Unit,
    private val schedule: (Long, () -> Unit) -> (() -> Unit),
    private val reportFailure: (Exception) -> Unit = {},
) {
    enum class Kind { DISCOVER, MTU, READ, WRITE, DESCRIPTOR }

    class Command<O : Any>(
        val owner: O,
        val kind: Kind,
        val key: String,
        val execute: () -> Unit,
        val failed: (Exception) -> Unit,
    ) {
        internal var cancelDeadline: (() -> Unit)? = null
    }

    private val pending = ArrayDeque<Command<O>>()
    private var active: Command<O>? = null
    private var cancellations = 0

    @Synchronized
    fun enqueue(command: Command<O>, timeoutMs: Long? = null, expired: (() -> Unit)? = null) {
        pending.addLast(command)
        if (timeoutMs != null) {
            command.cancelDeadline = schedule(timeoutMs) {
                val stillPending = synchronized(this) { contains(command) }
                if (stillPending) {
                    // Teardown may take service locks: never run it under the queue monitor.
                    val timeout = IllegalStateException("GATT ${command.kind} timed out")
                    try {
                        if (expired != null) expired() else cancelCommand(command, timeout)
                    } catch (e: Exception) {
                        try { reportFailure(e) } finally { cancelOwner(command.owner, timeout) }
                    }
                }
            }
        }
        startNext()
    }

    @Synchronized
    fun matches(owner: O, kind: Kind, key: String = ""): Boolean =
        active?.let { it.owner === owner && it.kind == kind && it.key == key } == true

    @Synchronized
    fun complete(owner: O, kind: Kind, key: String = "", result: () -> Unit = {}): Boolean {
        if (!matches(owner, kind, key)) return false
        val command = active!!
        // Retain the slot while delivering the result, including reentrant enqueue.
        try {
            result()
        } catch (e: Exception) {
            reportFailure(e)
        } finally {
            if (active === command) {
                command.cancelDeadline?.invoke()
                active = null
                startNext()
            }
        }
        return true
    }

    private fun cancelCommand(command: Command<O>, cause: Exception) {
        synchronized(this) {
            if (!contains(command)) return
            pending.remove(command)
            if (active === command) active = null
            cancellations++
        }
        deliverCancelled(listOf(command), cause)
    }

    fun cancelOwner(owner: O, cause: Exception) {
        val removed = synchronized(this) {
            val commands = pending.filter { it.owner === owner }.toMutableList()
            pending.removeAll { it.owner === owner }
            active?.takeIf { it.owner === owner }?.let {
                commands.add(0, it)
                active = null
            }
            cancellations++
            commands
        }
        deliverCancelled(removed, cause)
    }

    private fun deliverCancelled(commands: List<Command<O>>, cause: Exception) {
        try {
            for (command in commands) {
                command.cancelDeadline?.invoke()
                // Cancellation consumers can take service locks or throw.
                try { command.failed(cause) } catch (e: Exception) { reportFailure(e) }
            }
        } finally {
            synchronized(this) { cancellations--; startNext() }
        }
    }

    private fun contains(command: Command<O>): Boolean = active === command || pending.any { it === command }

    private fun startNext() {
        if (active != null || cancellations > 0 || pending.isEmpty()) return
        val command = pending.removeFirst()
        active = command
        post {
            synchronized(this) {
                // Cleanup may cancel a command after it was posted but before it runs.
                if (active !== command) return@synchronized
                try {
                    command.execute()
                } catch (e: Exception) {
                    if (active === command) complete(command.owner, command.kind, command.key) { command.failed(e) }
                }
            }
        }
    }
}
