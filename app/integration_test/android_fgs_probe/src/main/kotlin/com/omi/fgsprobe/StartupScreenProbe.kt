package com.omi.fgsprobe

import android.app.Activity
import android.app.Instrumentation
import android.os.Bundle
import android.os.SystemClock
import android.util.Xml
import android.view.accessibility.AccessibilityNodeInfo
import java.io.StringWriter
import org.xmlpull.v1.XmlSerializer

/** Reads real accessibility content without waiting for animated UI to idle. */
class StartupScreenProbe : Instrumentation() {
    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        start()
    }

    override fun onStart() {
        val result = Bundle()
        try {
            val automation = uiAutomation
            val deadline = SystemClock.uptimeMillis() + 10000
            var screen = ""
            do {
                val root = automation.rootInActiveWindow
                if (root != null) {
                    val writer = StringWriter()
                    val xml = Xml.newSerializer()
                    xml.setOutput(writer)
                    xml.startTag(null, "screen")
                    xml.attribute(null, "package", root.packageName?.toString() ?: "")
                    appendNode(xml, root)
                    xml.endTag(null, "screen")
                    xml.flush()
                    screen = writer.toString()
                    if (screen.contains("Get Started", ignoreCase = true)) break
                }
                SystemClock.sleep(500)
            } while (SystemClock.uptimeMillis() < deadline)
            result.putString("screen", screen)
            finish(Activity.RESULT_OK, result)
        } catch (error: Exception) {
            result.putString("error", error.toString())
            finish(Activity.RESULT_CANCELED, result)
        }
    }

    private fun appendNode(xml: XmlSerializer, node: AccessibilityNodeInfo) {
        xml.startTag(null, "node")
        xml.attribute(null, "text", node.text?.toString() ?: "")
        xml.attribute(null, "description", node.contentDescription?.toString() ?: "")
        for (index in 0 until node.childCount) {
            node.getChild(index)?.let { appendNode(xml, it) }
        }
        xml.endTag(null, "node")
    }
}
