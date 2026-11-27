package com.friend.ios

import android.content.Context
import android.system.Os
import android.system.OsConstants
import java.io.File
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/** Directory fsync bridge shared by UI and headless Flutter engines. */
object LiveWalReceiptDurabilityChannel {
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

    fun register(context: Context, engine: FlutterEngine) {
        MethodChannel(engine.dartExecutor.binaryMessenger, "com.omi/live_wal_receipt_durability")
            .setMethodCallHandler { call, result ->
                if (call.method != "syncDirectory") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val rawPath = call.argument<String>("path")
                if (rawPath == null) {
                    result.error("invalid_path", "directory path is required", null)
                    return@setMethodCallHandler
                }
                try {
                    val directory = checkedDirectory(context, rawPath)
                    val fd = Os.open(directory.path, OsConstants.O_RDONLY or OsConstants.O_DIRECTORY, 0)
                    try {
                        Os.fsync(fd)
                    } finally {
                        Os.close(fd)
                    }
                    result.success(null)
                } catch (error: Exception) {
                    result.error("directory_sync_failed", error.message ?: error.javaClass.simpleName, null)
                }
            }
    }
}
