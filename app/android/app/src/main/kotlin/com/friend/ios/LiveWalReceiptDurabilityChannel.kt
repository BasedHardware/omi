package com.friend.ios

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.system.Os
import android.system.OsConstants
import java.io.File
import java.util.concurrent.Executors
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/** Directory fsync bridge shared by UI and headless Flutter engines. */
object LiveWalReceiptDurabilityChannel {
    // Android's OsConstants omits this Linux ABI flag on some SDK stubs.
    private const val O_DIRECTORY = 0x10000
    private val ioExecutor = Executors.newSingleThreadExecutor { task ->
        Thread(task, "omi-live-wal-durability").apply { isDaemon = true }
    }
    private val mainHandler = Handler(Looper.getMainLooper())
    internal var directoryFsyncForTesting: ((File) -> Unit)? = null

    internal fun documentsDirectory(context: Context): File =
        context.getDir("flutter", Context.MODE_PRIVATE).canonicalFile

    internal fun checkedDirectory(context: Context, rawPath: String): File {
        val root = documentsDirectory(context)
        val directory = File(rawPath).canonicalFile
        if ((directory != root && !directory.path.startsWith(root.path + File.separator)) ||
            !directory.isDirectory
        ) {
            throw SecurityException("directory is outside app documents")
        }
        return directory
    }

    internal fun syncDirectory(context: Context, rawPath: String) {
        val directory = checkedDirectory(context, rawPath)
        val override = directoryFsyncForTesting
        if (override != null) {
            override(directory)
            return
        }
        val fd = Os.open(directory.path, OsConstants.O_RDONLY or O_DIRECTORY, 0)
        try {
            Os.fsync(fd)
        } finally {
            Os.close(fd)
        }
    }

    fun register(context: Context, engine: FlutterEngine) {
        MethodChannel(engine.dartExecutor.binaryMessenger, "com.omi/live_wal_receipt_durability")
            .setMethodCallHandler { call, result -> handle(context, call, result) }
    }

    internal fun handle(context: Context, call: MethodCall, result: MethodChannel.Result) {
        if (call.method != "syncDirectory") {
            result.notImplemented()
            return
        }
        val rawPath = call.argument<String>("path")
        if (rawPath == null) {
            result.error("invalid_path", "directory path is required", null)
            return
        }
        ioExecutor.execute {
            val error = try {
                syncDirectory(context, rawPath)
                null
            } catch (caught: Throwable) {
                caught
            }
            mainHandler.post {
                if (error == null) {
                    result.success(null)
                } else {
                    val code = if (error is SecurityException) "invalid_path" else "directory_sync_failed"
                    result.error(code, error.message ?: error.javaClass.simpleName, null)
                }
            }
        }
    }
}
