package com.friend.ios.phonemic

/**
 * Pigeon adapter: forwards host-API calls straight to the controller. No logic lives
 * here — the controller confines itself to the main thread and resolves the Pigeon
 * callbacks itself (the Kotlin peer of iOS `PhoneMicHostApiImpl`).
 */
class PhoneMicHostApiImpl(private val controller: PhoneMicController) : PhoneMicHostApi {
    override fun start(mode: PhoneMicCaptureMode, callback: (Result<Unit>) -> Unit) =
        controller.start(mode, callback)

    override fun stop(callback: (Result<Unit>) -> Unit) =
        controller.stop(callback)

    override fun isRecording(): Boolean = controller.isRecording
}
