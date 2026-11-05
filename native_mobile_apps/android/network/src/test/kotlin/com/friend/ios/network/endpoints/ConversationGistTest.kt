package com.friend.ios.network.endpoints

import com.friend.ios.network.generated.OmiAPI
import com.friend.ios.network.generated.OmiJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** `ConversationMapper.detail`'s gist, as iOS `ConversationMapper` reads `structured.short_summary`. */
class ConversationGistTest {
    private fun conversation(sections: String, apps: String = "[]") = OmiJson.decodeFromString(
        OmiAPI.Conversation.serializer(),
        """
        {"id": "c1", "created_at": "2026-10-08T07:15:00Z", "started_at": "2026-10-08T07:00:00Z", "status": "completed",
         "structured": {"title": "Roadmap", "overview": "", "short_summary": "  Ship before the holidays.  ", "sections": $sections},
         "transcript_segments": [], "apps_results": $apps}
        """.trimIndent(),
    )

    @Test
    fun omisOwnSummaryLeadsWithTheGist() {
        val detail = ConversationMapper.detail(conversation("""[{"heading": "Decisions", "body_markdown": "Ship it."}]"""))
        assertEquals("Ship before the holidays.", detail.gist)
    }

    @Test
    fun anEditedSummaryOrAnAppsResultHasNoGist() {
        // Editing Omi's summary drops the generated sections, and the old gist with them.
        assertNull(ConversationMapper.detail(conversation("[]")).gist)
        val app = """[{"app_id": "notes", "content": "The app's summary."}]"""
        assertNull(ConversationMapper.detail(conversation("""[{"heading": "Decisions", "body_markdown": "Ship it."}]""", app)).gist)
    }
}
