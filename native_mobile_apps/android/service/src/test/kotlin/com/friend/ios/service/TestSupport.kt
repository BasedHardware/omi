package com.friend.ios.service

import android.content.SharedPreferences
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Proxy

/**
 * Port of `OmiTestSupport`: a fake API and in-memory preferences for store tests.
 *
 * `fakeAPI { "subscription" returns ...; "setVocabulary" does { args -> ... } }`: every call not
 * stubbed throws [NotImplementedError]; suspend functions are answered directly (the proxy returns
 * the value instead of suspending). Calls are recorded in [FakeAPI.calls].
 */
@Suppress("UNCHECKED_CAST")
class FakeAPI {
    val calls = mutableListOf<Pair<String, List<Any?>>>()
    private val answers = HashMap<String, (List<Any?>) -> Any?>()

    infix fun String.returns(value: Any?) {
        answers[this] = { value }
    }

    infix fun String.does(answer: (List<Any?>) -> Any?) {
        answers[this] = answer
    }

    infix fun String.throws(error: Throwable) {
        answers[this] = { throw error }
    }

    fun called(name: String): List<List<Any?>> = calls.filter { it.first == name }.map { it.second }

    val client: APIClientProtocol = Proxy.newProxyInstance(
        APIClientProtocol::class.java.classLoader,
        arrayOf(APIClientProtocol::class.java),
        InvocationHandler { _, method, rawArgs ->
            if (method.declaringClass == Any::class.java) {
                return@InvocationHandler when (method.name) {
                    "hashCode" -> System.identityHashCode(this)
                    "equals" -> rawArgs?.getOrNull(0) === this
                    else -> "FakeAPI"
                }
            }
            // A suspend function's last argument is its Continuation; it is not part of the call.
            val continuation = rawArgs?.lastOrNull() as? kotlin.coroutines.Continuation<Any?>
            val args = rawArgs.orEmpty().toList().let { if (continuation != null) it.dropLast(1) else it }
            calls += method.name to args
            val answer = answers[method.name] ?: throw NotImplementedError("FakeAPI: ${method.name} not stubbed")
            try {
                answer(args) ?: Unit
            } catch (e: Throwable) {
                // A checked exception thrown from a proxy arrives wrapped (UndeclaredThrowableException);
                // failing the continuation delivers the original error to the suspend caller.
                if (continuation == null) throw e
                continuation.resumeWith(Result.failure(e))
                kotlin.coroutines.intrinsics.COROUTINE_SUSPENDED
            }
        },
    ) as APIClientProtocol
}

fun fakeAPI(setup: FakeAPI.() -> Unit = {}): FakeAPI = FakeAPI().apply(setup)

/** `freshPreferences()`: `Preferences` over an in-memory `SharedPreferences`. */
fun freshPreferences(): Preferences = Preferences(InMemorySharedPreferences())

class InMemorySharedPreferences : SharedPreferences {
    private val values = HashMap<String, Any?>()

    override fun getAll(): MutableMap<String, *> = HashMap(values)
    override fun getString(key: String, defValue: String?): String? = values[key] as? String ?: defValue
    @Suppress("UNCHECKED_CAST")
    override fun getStringSet(key: String, defValues: MutableSet<String>?): MutableSet<String>? = values[key] as? MutableSet<String> ?: defValues
    override fun getInt(key: String, defValue: Int): Int = values[key] as? Int ?: defValue
    override fun getLong(key: String, defValue: Long): Long = values[key] as? Long ?: defValue
    override fun getFloat(key: String, defValue: Float): Float = values[key] as? Float ?: defValue
    override fun getBoolean(key: String, defValue: Boolean): Boolean = values[key] as? Boolean ?: defValue
    override fun contains(key: String): Boolean = key in values
    override fun registerOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}
    override fun unregisterOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}

    override fun edit(): SharedPreferences.Editor = object : SharedPreferences.Editor {
        private val pending = HashMap<String, Any?>()
        private val removed = HashSet<String>()
        private var clear = false
        override fun putString(key: String, value: String?) = apply { pending[key] = value }
        override fun putStringSet(key: String, values: MutableSet<String>?) = apply { pending[key] = values }
        override fun putInt(key: String, value: Int) = apply { pending[key] = value }
        override fun putLong(key: String, value: Long) = apply { pending[key] = value }
        override fun putFloat(key: String, value: Float) = apply { pending[key] = value }
        override fun putBoolean(key: String, value: Boolean) = apply { pending[key] = value }
        override fun remove(key: String) = apply { removed += key }
        override fun clear() = apply { clear = true }
        override fun commit(): Boolean {
            apply()
            return true
        }
        override fun apply() {
            if (clear) values.clear()
            removed.forEach { values.remove(it) }
            pending.forEach { (k, v) -> if (v == null) values.remove(k) else values[k] = v }
        }
    }
}
