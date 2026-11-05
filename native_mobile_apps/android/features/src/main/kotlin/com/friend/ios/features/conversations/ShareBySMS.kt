package com.friend.ios.features.conversations

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.shareURL
import com.friend.ios.design.L
import com.friend.ios.service.LocalConversationsStore
import kotlinx.coroutines.delay

/**
 * Port of `ShareBySMS.swift` ("Share via SMS", Flutter `share_to_contacts_sheet`): the messaging
 * app opens with "Here's what we just discussed: <link>". Omi never sends anything; the user sends
 * from the composer. The link needs the conversation shared, so a private one is shared first.
 *
 * Android deviation: iOS picks the contacts' numbers first (`CNContactPickerViewController`) and
 * learns from `MFMessageComposeViewController` whether the message went out, going back to private
 * when it did not. Android's `ACTION_SENDTO smsto:` lets the user pick recipients in the messaging
 * app and reports nothing back, so the conversation stays shared once the composer opened.
 */
@Composable
fun ShareBySMS(isActive: Boolean, onActiveChange: (Boolean) -> Unit, conversation: Conversation, onNotice: (String) -> Unit) {
    val conversations = LocalConversationsStore.current
    val prepareFailed = L("failedToPrepareConversationForSharing")
    val noSmsApp = L("couldNotOpenSmsApp")
    val link = Conversation.shareURL(conversation.id)
    val body = L("heresWhatWeDiscussed", link)
    // The composer reports no result; nothing more happens when it returns.
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {}
    LaunchedEffect(isActive) {
        if (!isActive) return@LaunchedEffect
        onActiveChange(false)
        val id = conversation.id
        val wasPrivate = conversation.visibility == Conversation.Visibility.Private
        if (wasPrivate && !conversations.setVisibility(id, Conversation.Visibility.Shared)) {
            onNotice(prepareFailed)
            return@LaunchedEffect
        }
        // As on iOS, a short pause so the composer does not open mid-transition.
        delay(300)
        try {
            launcher.launch(Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:")).putExtra("sms_body", body))
        } catch (e: ActivityNotFoundException) {
            if (wasPrivate) conversations.setVisibility(id, Conversation.Visibility.Private)
            onNotice(noSmsApp)
        }
    }
}
