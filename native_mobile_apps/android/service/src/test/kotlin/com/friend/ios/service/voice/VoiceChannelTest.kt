package com.friend.ios.service.voice

import com.friend.ios.network.listen.ListenEvent
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import com.friend.ios.network.listen.LiveSegment as ListenSegment
import com.friend.ios.network.listen.LiveTranscriptionChannel as ListenChannel

/** Onboarding's server words come from the listen socket's transcription-only channel. */
class VoiceChannelTest {
    private class FakeListenChannel(override val events: Flow<ListenEvent>) : ListenChannel {
        val audio = mutableListOf<ByteArray>()
        val closes = mutableListOf<String>()

        override fun send(audio: ByteArray) {
            this.audio += audio
        }

        override fun sendSuggestedTranscript(segments: List<ListenSegment>, provider: String) = Unit

        override fun close(reason: String) {
            closes += reason
        }
    }

    @Test
    fun segmentsAndStatusPassEverythingElseStays() = runTest {
        val segment = ListenSegment("s1", "Hello there", speaker = null, speakerID = null, isUser = true, start = 0.5, end = 1.25)
        val socket = FakeListenChannel(
            flowOf(ListenEvent.Status("ready"), ListenEvent.ConversationStarted("c1"), ListenEvent.Segments(listOf(segment))),
        )
        val channel = socket.asVoiceChannel()
        assertEquals(
            listOf(
                LiveTranscriptionChannel.Event.Status("ready"),
                LiveTranscriptionChannel.Event.Segments(listOf(LiveSegment("s1", "Hello there", "SPEAKER_00", 0, true, 0.5, 1.25))),
            ),
            channel.events.toList(),
        )
        channel.send(byteArrayOf(1, 2))
        channel.close("onboarding")
        assertEquals(1, socket.audio.size)
        assertEquals(listOf("onboarding"), socket.closes)
    }
}
