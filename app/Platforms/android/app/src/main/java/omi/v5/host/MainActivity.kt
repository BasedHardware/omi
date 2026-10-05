package omi.v5.host

import android.app.Application
import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment

import omi.kit.KeyValueStoring
import omi.kit.PreferenceValue
import omi.kit.SettingsStore
import omi.ui.AppServices
import omi.ui.AppStore
import omi.ui.RootView
import skip.foundation.ProcessInfo
import skip.ui.ColorScheme
import skip.ui.ComposeContext
import skip.ui.PresentationRoot
import skip.ui.UIApplication

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
class OmiApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        ProcessInfo.launch(applicationContext)
        OmiPolicyJniBridge.installOnce(applicationContext)
    }
}

class MainActivity : AppCompatActivity() {
    private lateinit var store: AppStore

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        OmiPolicyJniBridge.installOnce(applicationContext)
        UIApplication.launch(this)
        enableEdgeToEdge()

        val services = AppServices(
            settings = SettingsStore(SharedPreferencesKeyValueStore(applicationContext)),
        )
        store = AppStore(services = services)
        applyIntent(intent)

        setContent {
            OmiPresentationRoot(store, ComposeContext())
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

@Composable
private fun OmiPresentationRoot(store: AppStore, context: ComposeContext) {
    val colorScheme = if (isSystemInDarkTheme()) ColorScheme.dark else ColorScheme.light
    PresentationRoot(defaultColorScheme = colorScheme, context = context) { ctx ->
        val contentContext = ctx.content()
        Box(modifier = ctx.modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            RootView().environmentObject(store).Compose(context = contentContext)
        }
    }
}

/// SharedPreferences backend for the whitelisted desktop preference keys
/// (bool vs integer discrimination mirrors the Apple hosts' CFBoolean rule).
class SharedPreferencesKeyValueStore(context: Context) : KeyValueStoring {
    private val preferences =
        context.getSharedPreferences("omi.v5.preferences", Context.MODE_PRIVATE)

    override fun value(forKey: String): PreferenceValue? {
        if (!preferences.contains(forKey)) return null
        return when (val raw = preferences.all[forKey]) {
            is Boolean -> PreferenceValue.bool(raw)
            is Int -> PreferenceValue.integer(raw)
            is Long -> PreferenceValue.integer(raw.toInt())
            is String -> PreferenceValue.string(raw)
            else -> null
        }
    }

    override fun set(value: PreferenceValue?, forKey: String) {
        val editor = preferences.edit()
        when (value) {
            null -> editor.remove(forKey)
            is PreferenceValue.BoolCase -> editor.putBoolean(forKey, value.associated0)
            is PreferenceValue.IntegerCase -> editor.putInt(forKey, value.associated0)
            is PreferenceValue.StringCase -> editor.putString(forKey, value.associated0)
        }
        editor.apply()
    }
}
