package com.friend.ios

object ForegroundAppDetector {
    @Volatile
    var currentPackage: String? = null
        private set

    fun update(packageName: String?) {
        currentPackage = packageName
        AmbientCaptureMethodChannel.emitHealth(
            mapOf(
                "state" to "FOREGROUND_APP_CHANGED",
                "foregroundPackage" to packageName,
                "timestamp" to System.currentTimeMillis(),
            ),
        )
    }
}
