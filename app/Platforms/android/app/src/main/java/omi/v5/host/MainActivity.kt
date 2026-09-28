package omi.v5.host

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier

import omi.kit.Policy
import omi.kit.PreferenceValue
import omi.kit.SettingsStore
import omi.ui.AppServices
import omi.ui.AppStore
import omi.ui.KeyValueStoring
import omi.ui.RootView

// Android host shell. Bootstrap + injection + intent plumbing only; all
// product UI comes from the skipstone-transpiled OmiUI RootView.
//
// Injection contract (see ../../README.md):
//   - `Policy.bridge` (omi.kit.NativePolicyBridge) is replaced at first
//     launch with OmiPolicyJniBridge, which binds the SAME native-core C++
//     the Apple hosts compile — the policy is never re-derived in Kotlin.
//   - Settings round-trip through SharedPreferences (whitelisted desktop
//     preference keys, same typing rules as the Apple hosts). The network,
//     auth, and BLE facades are injected by their Kotlin ports when they
//     land; absent facades degrade honestly (the store keeps the Welcome
//     gate instead of faking a signed-in shell).
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        OmiPolicyJniBridge.installOnce(applicationContext)

        val services = AppServices(
            settings = SettingsStore(SharedPreferencesKeyValueStore(applicationContext)),
        )
        val store = AppStore(services = services)
        applyIntent(intent)

        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    // Same composition as the Apple hosts:
                    // RootView().environmentObject(store).
                    RootView().environmentObject(store)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        applyIntent(intent)
    }

    /// `omi-rnruntime://auth/callback?...` returns from the PKCE browser
    /// intent. The native session module (ported from
    /// react-native/android/.../OmiAuthModule.kt) owns the token exchange;
    /// the host only routes the URL and must never see tokens.
    private fun applyIntent(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme == "omi-rnruntime" && data.host == "auth") {
            // hand off to the session seam once injected
        }
    }
}

/// SharedPreferences backend for the whitelisted desktop preference keys
/// (bool vs integer discrimination mirrors the Apple hosts' CFBoolean rule).
class SharedPreferencesKeyValueStore(context: Context) : KeyValueStoring {
    private val preferences =
        context.getSharedPreferences("omi.v5.preferences", Context.MODE_PRIVATE)

    override fun value(key: String): PreferenceValue? {
        if (!preferences.contains(key)) return null
        return when (val raw = preferences.all[key]) {
            is Boolean -> PreferenceValue.Bool(raw)
            is Int -> PreferenceValue.Int(raw)
            is Long -> PreferenceValue.Int(raw.toInt())
            is String -> PreferenceValue.Str(raw)
            else -> null
        }
    }

    override fun set(value: PreferenceValue?, key: String) {
        val editor = preferences.edit()
        when (value) {
            null -> editor.remove(key)
            is PreferenceValue.Bool -> editor.putBoolean(key, value.value)
            is PreferenceValue.Int -> editor.putInt(key, value.value)
            is PreferenceValue.Str -> editor.putString(key, value.value)
        }
        editor.apply()
    }
}
