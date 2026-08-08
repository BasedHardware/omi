package com.lynxshell.providers

import android.content.Context
import com.lynx.tasm.provider.AbsTemplateProvider
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class TemplateProvider(context: Context) : AbsTemplateProvider() {

    private var mContext: Context = context.applicationContext

    override fun loadTemplate(uri: String, callback: Callback) {
        Thread {
            if (uri.startsWith("http")) {
                var connection: HttpURLConnection? = null
                try {
                    val url = URL(uri)
                    connection = url.openConnection() as HttpURLConnection

                    connection.apply {
                        requestMethod = "GET"
                        connectTimeout = 10000
                        readTimeout = 15000
                    }

                    val responseCode = connection.responseCode

                    if (responseCode in 200..299) {
                        connection.inputStream.use { inputStream ->
                            ByteArrayOutputStream().use { byteArrayOutputStream ->
                                val buffer = ByteArray(1024)
                                var length: Int
                                while ((inputStream.read(buffer).also { length = it }) != -1) {
                                    byteArrayOutputStream.write(buffer, 0, length)
                                }
                                callback.onSuccess(byteArrayOutputStream.toByteArray())
                            }
                        }
                    } else {
                        callback.onFailed("HTTP Error: $responseCode")
                    }

                } catch (e: IOException) {
                    callback.onFailed("Network error: ${e.message}")
                } catch (e: Exception) {
                    callback.onFailed("Error loading template: ${e.message}")
                } finally {
                    connection?.disconnect()
                }
            } else {
                try {
                    mContext.assets.open(uri).use { inputStream ->
                        ByteArrayOutputStream().use { byteArrayOutputStream ->
                            val buffer = ByteArray(1024)
                            var length: Int
                            while ((inputStream.read(buffer).also { length = it }) != -1) {
                                byteArrayOutputStream.write(buffer, 0, length)
                            }
                            callback.onSuccess(byteArrayOutputStream.toByteArray())
                        }
                    }
                } catch (e: IOException) {
                    callback.onFailed(e.message)
                }
            }
        }.start()
    }
}
