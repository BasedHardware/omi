package com.friend.ios

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.Log
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import org.json.JSONObject

class LocalYoloePlugin(private val context: Context) : MethodChannel.MethodCallHandler {
    companion object {
        private const val TAG = "LocalYoloePlugin"
        private const val CHANNEL_NAME = "com.omi/local_yoloe"
        private const val INPUT_SIZE = 640

        init {
            try {
                System.loadLibrary("local_yoloe")
            } catch (e: UnsatisfiedLinkError) {
                Log.e(TAG, "Failed to load local_yoloe native library", e)
            }
        }

        fun registerWith(flutterEngine: FlutterEngine, context: Context) {
            MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL_NAME)
                .setMethodCallHandler(LocalYoloePlugin(context.applicationContext))
        }
    }

    private val executor: ExecutorService = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "local-yoloe-inference").apply { isDaemon = true }
    }
    private val labels = mutableListOf<String>()
    private var nativeHandle: Long = 0L

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "loadModel" -> executor.execute { handleLoadModel(call, result) }
            "detectJpeg" -> executor.execute { handleDetectJpeg(call, result) }
            "close" -> executor.execute { handleClose(result) }
            else -> result.notImplemented()
        }
    }

    private fun handleLoadModel(call: MethodCall, result: MethodChannel.Result) {
        try {
            val modelDirectory = call.argument<String>("modelDirectory")
                ?: error("Missing modelDirectory")
            val modelDir = copyModelAssets(modelDirectory)
            labels.clear()
            labels.addAll(loadLabels(File(modelDir, "labels.json")))

            if (nativeHandle != 0L) nativeClose(nativeHandle)
            nativeHandle = nativeLoad(
                File(modelDir, "model.ncnn.param").absolutePath,
                File(modelDir, "model.ncnn.bin").absolutePath,
            )
            if (nativeHandle == 0L) error("NCNN model load failed")
            result.success(true)
        } catch (e: Throwable) {
            Log.e(TAG, "loadModel failed", e)
            result.error("LOCAL_YOLOE_LOAD_FAILED", e.message, null)
        }
    }

    private fun handleDetectJpeg(call: MethodCall, result: MethodChannel.Result) {
        try {
            val totalStartedAt = System.nanoTime()
            if (nativeHandle == 0L) error("Model is not loaded")
            val bytes = call.argument<ByteArray>("bytes") ?: error("Missing JPEG bytes")
            val confidenceThreshold = (call.argument<Double>("confidenceThreshold") ?: 0.25).toFloat()
            val iouThreshold = (call.argument<Double>("iouThreshold") ?: 0.45).toFloat()
            val maxDetections = call.argument<Int>("maxDetections") ?: 20

            val preprocessStartedAt = System.nanoTime()
            val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: error("Failed to decode JPEG")
            val letterbox = letterbox(decoded)
            if (letterbox.bitmap != decoded) decoded.recycle()

            val pixels = IntArray(INPUT_SIZE * INPUT_SIZE)
            letterbox.bitmap.getPixels(pixels, 0, INPUT_SIZE, 0, 0, INPUT_SIZE, INPUT_SIZE)
            letterbox.bitmap.recycle()
            val preprocessMs = elapsedMs(preprocessStartedAt)

            val inferenceStartedAt = System.nanoTime()
            val raw = nativeDetect(nativeHandle, pixels, INPUT_SIZE, INPUT_SIZE, confidenceThreshold, iouThreshold, maxDetections)
            val inferenceMs = elapsedMs(inferenceStartedAt)

            val postprocessStartedAt = System.nanoTime()
            val detections = mapDetections(raw, letterbox)
            val postprocessMs = elapsedMs(postprocessStartedAt)
            result.success(
                mapOf(
                    "detections" to detections,
                    "latencyMs" to mapOf(
                        "preprocess" to preprocessMs,
                        "inference" to inferenceMs,
                        "postprocess" to postprocessMs,
                        "total" to elapsedMs(totalStartedAt),
                    ),
                ),
            )
        } catch (e: Throwable) {
            Log.e(TAG, "detectJpeg failed", e)
            result.error("LOCAL_YOLOE_DETECT_FAILED", e.message, null)
        }
    }

    private fun elapsedMs(startedAt: Long): Double = (System.nanoTime() - startedAt) / 1_000_000.0

    private fun handleClose(result: MethodChannel.Result) {
        try {
            if (nativeHandle != 0L) nativeClose(nativeHandle)
            nativeHandle = 0L
            result.success(true)
        } catch (e: Throwable) {
            result.error("LOCAL_YOLOE_CLOSE_FAILED", e.message, null)
        }
    }

    private fun copyModelAssets(modelDirectory: String): File {
        val targetDir = File(context.filesDir, "local_yoloe/$modelDirectory")
        targetDir.mkdirs()
        for (name in listOf("model.ncnn.param", "model.ncnn.bin", "labels.json")) {
            val outFile = File(targetDir, name)
            if (outFile.exists() && outFile.length() > 0) continue
            context.assets.open("flutter_assets/$modelDirectory/$name").use { input ->
                FileOutputStream(outFile).use { output -> input.copyTo(output) }
            }
        }
        return targetDir
    }

    private fun loadLabels(file: File): List<String> {
        val json = JSONObject(file.readText())
        val array = json.getJSONArray("labels")
        return List(array.length()) { index -> array.getJSONObject(index).getString("name") }
    }

    private fun letterbox(source: Bitmap): LetterboxResult {
        val scale = minOf(INPUT_SIZE.toFloat() / source.width, INPUT_SIZE.toFloat() / source.height)
        val resizedWidth = (source.width * scale).toInt().coerceAtLeast(1)
        val resizedHeight = (source.height * scale).toInt().coerceAtLeast(1)
        val dx = (INPUT_SIZE - resizedWidth) / 2f
        val dy = (INPUT_SIZE - resizedHeight) / 2f

        val output = Bitmap.createBitmap(INPUT_SIZE, INPUT_SIZE, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(output)
        canvas.drawColor(Color.rgb(114, 114, 114))
        val resized = Bitmap.createScaledBitmap(source, resizedWidth, resizedHeight, true)
        canvas.drawBitmap(resized, dx, dy, Paint(Paint.FILTER_BITMAP_FLAG))
        resized.recycle()

        return LetterboxResult(
            bitmap = output,
            originalWidth = source.width,
            originalHeight = source.height,
            scale = scale,
            padX = dx,
            padY = dy,
        )
    }

    private fun mapDetections(raw: FloatArray, letterbox: LetterboxResult): List<Map<String, Any>> {
        val output = mutableListOf<Map<String, Any>>()
        var offset = 0
        while (offset + 5 < raw.size) {
            val classId = raw[offset].toInt()
            val confidence = raw[offset + 1]
            val x0 = ((raw[offset + 2] - letterbox.padX) / letterbox.scale).coerceIn(0f, letterbox.originalWidth.toFloat())
            val y0 = ((raw[offset + 3] - letterbox.padY) / letterbox.scale).coerceIn(0f, letterbox.originalHeight.toFloat())
            val x1 = ((raw[offset + 4] - letterbox.padX) / letterbox.scale).coerceIn(0f, letterbox.originalWidth.toFloat())
            val y1 = ((raw[offset + 5] - letterbox.padY) / letterbox.scale).coerceIn(0f, letterbox.originalHeight.toFloat())
            val width = (x1 - x0).coerceAtLeast(0f)
            val height = (y1 - y0).coerceAtLeast(0f)
            if (classId in labels.indices && width > 0f && height > 0f) {
                output.add(
                    mapOf(
                        "label" to labels[classId],
                        "confidence" to confidence.toDouble(),
                        "box" to mapOf(
                            "left" to (x0 / letterbox.originalWidth).toDouble(),
                            "top" to (y0 / letterbox.originalHeight).toDouble(),
                            "width" to (width / letterbox.originalWidth).toDouble(),
                            "height" to (height / letterbox.originalHeight).toDouble(),
                        ),
                    ),
                )
            }
            offset += 6
        }
        return output
    }

    private data class LetterboxResult(
        val bitmap: Bitmap,
        val originalWidth: Int,
        val originalHeight: Int,
        val scale: Float,
        val padX: Float,
        val padY: Float,
    )

    private external fun nativeLoad(paramPath: String, binPath: String): Long
    private external fun nativeDetect(
        handle: Long,
        argbPixels: IntArray,
        width: Int,
        height: Int,
        confidenceThreshold: Float,
        iouThreshold: Float,
        maxDetections: Int,
    ): FloatArray
    private external fun nativeClose(handle: Long)
}