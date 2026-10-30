package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationPerson
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant

class EntityVisualTest {
    private fun conversation(people: List<ConversationPerson> = emptyList(), emoji: String? = "📈", category: String? = "business") = Conversation(
        id = "c", title = "Investor call with Northwind", overview = "", emoji = emoji, category = category,
        createdAt = Instant.EPOCH, startedAt = null, finishedAt = null, status = Conversation.Status.Completed,
        isStarred = false, actionItemCount = 0, people = people,
    )

    private fun task(text: String) = ActionItem(id = "t", description = text, isCompleted = false, dueAt = null, conversationID = "c", owner = ActionItem.Owner.User, workstreamID = null, createdAt = null)

    @Test fun namedServiceWins() {
        assertEquals(EntityVisual.Brand("gmail.com", "gmail"), EntityVisual.forTask(task("Send the deck via Gmail"), conversation()))
    }

    @Test fun companyAddressGivesItsDomain() {
        val people = listOf(ConversationPerson("Maya", "maya@mail.stripe.com", null))
        assertEquals(EntityVisual.Brand("stripe.com"), EntityVisual.forTask(task("Draft the memo"), conversation(people)))
    }

    @Test fun freemailAndPlaceholdersNeverBrand() {
        val people = listOf(ConversationPerson("Anna Keller", "anna@example.com", null), ConversationPerson(null, "leo@gmail.com", null))
        assertEquals(EntityVisual.Person("Anna Keller", "anna@example.com"), EntityVisual.forTask(task("Send Anna the follow-up"), conversation(people)))
    }

    @Test fun titleGuessesAreNotBrands() {
        // "Northwind" alone is a name, not a domain: the emoji stays.
        assertEquals(EntityVisual.Emoji("📈", "business"), EntityVisual.forTask(task("Northwind sends term sheet draft"), conversation()))
    }

    @Test fun categoryGlyphWithoutEmoji() {
        assertEquals(EntityVisual.Symbol("heart"), EntityVisual.forTask(task("Book physio"), conversation(emoji = null, category = "health")))
    }
}
