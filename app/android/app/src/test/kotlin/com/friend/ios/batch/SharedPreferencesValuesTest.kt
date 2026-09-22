package com.friend.ios.batch

import android.content.SharedPreferences
import org.junit.Assert.*
import org.junit.Test
import java.lang.reflect.Proxy

class SharedPreferencesValuesTest {
    @Test fun `typed reads handle Flutter scalar representations without copying all preferences`() {
        val values = mutableMapOf<String, Any>("flutter.text" to "value", "flutter.bool" to true,
            "flutter.long" to 45L, "flutter.int" to 90, "flutter.numericString" to "120",
            "flutter.boolString" to "true")
        val prefs = Proxy.newProxyInstance(SharedPreferences::class.java.classLoader,
            arrayOf(SharedPreferences::class.java)) { _, method, args ->
            check(method.name != "getAll") { "getAll must not be used in the audio hot path" }
            val value = values[args!![0]] ?: args[1]
            when (method.name) {
                "getString" -> value as String?
                "getBoolean" -> value as Boolean
                "getLong" -> value as Long
                "getInt" -> value as Int
                "getFloat" -> value as Float
                else -> error("Unexpected preference access: ${method.name}")
            }
        } as SharedPreferences
        val reader = SharedPreferencesValues(prefs)
        assertEquals("value", reader.string("text"))
        assertEquals("true", reader.string("bool"))
        assertTrue(reader.boolean("bool"))
        assertTrue(reader.boolean("boolString"))
        assertFalse(reader.boolean("text"))
        assertEquals(45, reader.integer("long", 0))
        assertEquals(90, reader.integer("int", 0))
        assertEquals(120, reader.integer("numericString", 0))
        assertEquals(13, reader.integer("text", 13))
        assertEquals("default", reader.string("missing", "default"))
        values["flutter.text"] = "updated"
        assertEquals("updated", reader.string("text"))
        values.clear()
        assertEquals("", reader.string("text"))
    }
}
