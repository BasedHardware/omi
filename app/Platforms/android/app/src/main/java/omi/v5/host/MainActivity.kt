package omi.v5.host

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier

import omi.kit.Policy
import omi.ui.AppModel
import omi.ui.MobileRoute
import omi.ui.RootView

// Android host shell. Bootstrap + injection + intent plumbing only; all
// product UI comes from the skipstone-transpiled OmiUI RootView.
//
// Injection contract (see ../../README.md):
//   - `Policy.bridge` (omi.kit.NativePolicyBridge) is replaced at first
//     launch with OmiPolicyJniBridge, which binds the SAME native-core C++
//     the Apple hosts compile — the policy is never re-derived in Kotlin.
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        OmiPolicyJniBridge.installOnce(applicationContext)

        val model = AppModel(route = MobileRoute.home, signedIn = false)
        applyIntent(intent)

        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    RootView(model = model)
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
