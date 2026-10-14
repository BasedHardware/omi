package com.friend.ios.system

import android.app.Activity
import android.content.Context
import android.content.Intent
import androidx.activity.ComponentActivity
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import com.friend.ios.ble.OmiCompanionManager
import kotlinx.coroutines.CompletableDeferred
import java.lang.ref.WeakReference
import java.util.UUID

/**
 * The pairing step's companion association (Flutter `BleHostApiImpl.requestCompanionDeviceAssociation`
 * + `OmiCompanionManager`): the system chooser for the Omi being paired, shown from the current
 * activity. With the association the system starts `BleCompanionService` when the Omi comes into
 * range, so the link starts in the background (Android 13+ presence observation).
 */
class CompanionPairing(context: Context) {
    private var activity = WeakReference<ComponentActivity>(null)
    private val manager = OmiCompanionManager(context.applicationContext) { activity.get() }

    /** Called from `MainActivity.onCreate`. */
    fun attach(activity: ComponentActivity) {
        this.activity = WeakReference(activity)
    }

    /** Associates [address]; quietly does nothing without an activity or when the user dismisses the chooser. */
    suspend fun associate(address: String) {
        val host = activity.get() ?: return
        manager.associateAndWait(address) { sender ->
            val result = CompletableDeferred<Intent?>()
            val launcher = host.activityResultRegistry.register(
                "omi.companion.${UUID.randomUUID()}", ActivityResultContracts.StartIntentSenderForResult(),
            ) { outcome -> result.complete(outcome.data.takeIf { outcome.resultCode == Activity.RESULT_OK }) }
            try {
                launcher.launch(IntentSenderRequest.Builder(sender).build())
                result.await()
            } finally {
                launcher.unregister()
            }
        }
    }
}
