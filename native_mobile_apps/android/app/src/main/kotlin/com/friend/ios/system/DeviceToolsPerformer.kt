package com.friend.ios.system

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.ContactsContract
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import com.friend.ios.core.models.ContactsAccess
import com.friend.ios.core.models.DeviceContact
import com.friend.ios.core.models.DeviceToolPerforming
import com.friend.ios.core.models.MessageComposeOutcome
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.ChatStore
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.lang.ref.WeakReference
import java.util.UUID

/**
 * Port of `DeviceToolsPerformer.swift`: the phone's side of Omi's device tools (backend
 * `utils/device_tools.py`): contacts lookups and the messaging app. Android cannot send a message
 * silently either, so the messaging app is the approval: the user sends (or not) there, and only
 * after tapping "Send" on "Omi asks" opened it. Android does not report whether it was sent
 * ([MessageComposeOutcome.Opened]).
 */
class DeviceToolsPerformer(private val context: Context) : DeviceToolPerforming {
    private var activity = WeakReference<ComponentActivity>(null)
    private val defaults = context.getSharedPreferences("omi.native", Context.MODE_PRIVATE)

    /** Called from `MainActivity.onCreate`: the permission prompt and the messaging app need it. */
    fun attach(activity: ComponentActivity) {
        this.activity = WeakReference(activity)
    }

    override val canSendMessages: Boolean
        get() = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:")).resolveActivity(context.packageManager) != null

    override val contactsAccess: ContactsAccess
        get() = when {
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED -> ContactsAccess.Granted
            defaults.getBoolean(ASKED_KEY, false) -> ContactsAccess.Denied
            else -> ContactsAccess.NotDetermined
        }

    override suspend fun requestContactsAccess(): ContactsAccess {
        if (contactsAccess == ContactsAccess.Granted) return contactsAccess
        val host = activity.get() ?: return contactsAccess
        val result = CompletableDeferred<Boolean>()
        val launcher = host.activityResultRegistry.register("omi.contacts.${UUID.randomUUID()}", ActivityResultContracts.RequestPermission()) {
            result.complete(it)
        }
        try {
            launcher.launch(Manifest.permission.READ_CONTACTS)
            result.await()
        } finally {
            launcher.unregister()
        }
        defaults.edit().putBoolean(ASKED_KEY, true).apply()
        return contactsAccess
    }

    override suspend fun searchContacts(query: String, limit: Int): List<DeviceContact> {
        if (!contactsAccess.isUsable) return emptyList()
        return withContext(Dispatchers.IO) { lookUp(query, limit.coerceIn(1, 50)) }
    }

    override suspend fun composeMessage(recipients: List<String>, text: String, subject: String?): MessageComposeOutcome {
        val host = activity.get() ?: return MessageComposeOutcome.Failed
        val emails = recipients.all { it.contains("@") }
        val intent = if (emails) {
            Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:" + recipients.joinToString(",")))
                .putExtra(Intent.EXTRA_TEXT, text)
                .apply { if (!subject.isNullOrEmpty()) putExtra(Intent.EXTRA_SUBJECT, subject) }
        } else {
            Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + Uri.encode(recipients.filter { !it.contains("@") }.joinToString(";"))))
                .putExtra("sms_body", text)
        }
        if (intent.resolveActivity(context.packageManager) == null) return MessageComposeOutcome.Unavailable
        val done = CompletableDeferred<Unit>()
        val launcher = host.activityResultRegistry.register("omi.compose.${UUID.randomUUID()}", ActivityResultContracts.StartActivityForResult()) {
            done.complete(Unit)
        }
        return try {
            launcher.launch(intent)
            // The user comes back from the messaging app; whether they sent is not reported.
            done.await()
            MessageComposeOutcome.Opened
        } catch (e: ActivityNotFoundException) {
            MessageComposeOutcome.Unavailable
        } finally {
            launcher.unregister()
        }
    }

    private fun lookUp(query: String, limit: Int): List<DeviceContact> {
        val resolver = context.contentResolver
        val uri = Uri.withAppendedPath(ContactsContract.Contacts.CONTENT_FILTER_URI, Uri.encode(query))
        val people = mutableListOf<Pair<String, String>>()
        resolver.query(uri, arrayOf(ContactsContract.Contacts._ID, ContactsContract.Contacts.DISPLAY_NAME_PRIMARY), null, null, null)?.use { cursor ->
            while (cursor.moveToNext() && people.size < limit) {
                people += cursor.getString(0) to (cursor.getString(1) ?: "")
            }
        }
        return people.map { (id, name) ->
            var mobile: String? = null
            val phones = mutableListOf<DeviceContact.Handle>()
            resolver.query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                arrayOf(ContactsContract.CommonDataKinds.Phone.NUMBER, ContactsContract.CommonDataKinds.Phone.TYPE, ContactsContract.CommonDataKinds.Phone.LABEL),
                "${ContactsContract.CommonDataKinds.Phone.CONTACT_ID} = ?", arrayOf(id), null,
            )?.use { cursor ->
                while (cursor.moveToNext()) {
                    val number = cursor.getString(0) ?: continue
                    val type = cursor.getInt(1)
                    val label = ContactsContract.CommonDataKinds.Phone.getTypeLabel(context.resources, type, cursor.getString(2)).toString()
                    phones += DeviceContact.Handle(label, number)
                    // The mobile number by its type, not its localized label.
                    if (mobile == null && type == ContactsContract.CommonDataKinds.Phone.TYPE_MOBILE) mobile = number
                }
            }
            val emails = mutableListOf<DeviceContact.Handle>()
            resolver.query(
                ContactsContract.CommonDataKinds.Email.CONTENT_URI,
                arrayOf(ContactsContract.CommonDataKinds.Email.ADDRESS, ContactsContract.CommonDataKinds.Email.TYPE, ContactsContract.CommonDataKinds.Email.LABEL),
                "${ContactsContract.CommonDataKinds.Email.CONTACT_ID} = ?", arrayOf(id), null,
            )?.use { cursor ->
                while (cursor.moveToNext()) {
                    val address = cursor.getString(0) ?: continue
                    val label = ContactsContract.CommonDataKinds.Email.getTypeLabel(context.resources, cursor.getInt(1), cursor.getString(2)).toString()
                    emails += DeviceContact.Handle(label, address)
                }
            }
            DeviceContact(
                id = id, name = name, phoneNumbers = phones, emailAddresses = emails,
                preferredHandle = mobile ?: phones.firstOrNull()?.value ?: emails.firstOrNull()?.value ?: "",
            )
        }
    }

    companion object {
        /** `UIApplication.shared.applicationState == .active`. */
        fun isInForeground(): Boolean {
            val info = android.app.ActivityManager.RunningAppProcessInfo()
            android.app.ActivityManager.getMyMemoryState(info)
            return info.importance == android.app.ActivityManager.RunningAppProcessInfo.IMPORTANCE_FOREGROUND
        }

        private const val ASKED_KEY = "omi.deviceTools.contactsAsked"

        /**
         * Runs end with a notification when the app is away; Omi can ask mid-run (a message to send,
         * which contact), and nothing happens without the user's tap.
         */
        fun wire(context: Context, agent: AgentStore, chat: ChatStore): DeviceToolsPerformer {
            agent.onRunEnded = { task, finished ->
                AgentNotifications.runEnded(context, task.id, task.description, finished, appInForeground = isInForeground())
            }
            val performer = DeviceToolsPerformer(context)
            agent.deviceTools = performer
            chat.deviceTools = performer
            return performer
        }
    }
}
