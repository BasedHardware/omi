package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.ConversationFilter
import com.friend.ios.core.models.ConversationQuery
import com.friend.ios.core.models.DailySummary
import com.friend.ios.core.models.Folder
import com.friend.ios.core.models.Goal
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.endpoints.ForYouItem
import java.lang.reflect.Proxy
import java.time.Instant

/**
 * The Home slice of `FakeAPIClient.swift`: conversations, tasks, goals and the "For you" feed in
 * memory. Every other API call (other areas' endpoints) fails, through a proxy, so this fake keeps
 * compiling when other ports add endpoints to [APIClientProtocol].
 */
class HomeFakeAPI(
    private val base: APIClientProtocol = unimplemented(),
) : APIClientProtocol by base {
    var conversationList = mutableListOf<Conversation>()
    var details = mutableMapOf<String, ConversationDetail>()
    var recapList = mutableListOf<DailySummary>()
    var folderList = mutableListOf<Folder>()
    var taskList = mutableListOf<ActionItem>()
    var goalList = mutableListOf<Goal>()
    var feed: List<ForYouItem>? = emptyList()
    var failing = false
    val calls = mutableListOf<String>()

    private fun check(call: String) {
        calls += call
        if (failing) throw IllegalStateException("offline")
    }

    override suspend fun conversations(limit: Int, offset: Int): List<Conversation> {
        check("conversations")
        return conversationList.drop(offset).take(limit)
    }

    override suspend fun conversations(limit: Int, offset: Int, filter: ConversationFilter): List<Conversation> {
        check("conversations.filter")
        return conversationList.filter(filter::keeps).drop(offset).take(limit)
    }

    override suspend fun conversations(limit: Int, offset: Int, query: ConversationQuery): List<Conversation> {
        check("conversations.query")
        return conversationList.filter { c ->
            (query.includeDiscarded || !c.isDiscarded) && (query.start?.let { c.date >= it } ?: true) && (query.end?.let { c.date <= it } ?: true)
        }.drop(offset).take(limit)
    }

    override suspend fun conversationDetail(id: String): ConversationDetail {
        check("detail.$id")
        return details[id] ?: throw IllegalStateException("404")
    }

    override suspend fun setConversationStarred(id: String, starred: Boolean) = check("star.$id.$starred")

    override suspend fun deleteConversation(id: String) {
        check("delete.$id")
        conversationList.removeAll { it.id == id }
    }

    override suspend fun folders(): List<Folder> {
        check("folders")
        return folderList
    }

    override suspend fun dailySummaries(limit: Int): List<DailySummary> {
        check("recaps")
        return recapList.take(limit)
    }

    override suspend fun createDailySummary(date: String): DailySummary? {
        check("recap.$date")
        return DailySummary("r-$date", date, "Written.", "", null, null, emptyList(), emptyList())
    }

    override suspend fun actionItems(limit: Int, offset: Int): List<ActionItem> {
        check("tasks")
        return taskList.drop(offset).take(limit)
    }

    override suspend fun setActionItem(id: String, completed: Boolean) = check("complete.$id.$completed")

    override suspend fun setActionItemStatus(id: String, status: ActionItem.Status, supersededBy: String?) = check("status.$id.${status.rawValue}")

    override suspend fun goals(): List<Goal> {
        check("goals")
        return goalList
    }

    override suspend fun setGoalProgress(id: String, current: Double): Goal {
        check("progress.$id")
        return goalList.first { it.id == id }.copy(current = current)
    }

    override suspend fun deleteGoal(id: String) = check("deleteGoal.$id")

    override suspend fun forYouFeed(): List<ForYouItem>? {
        check("feed")
        return feed
    }

    override suspend fun sendForYouFeedback(itemID: String, feedback: ForYouItem.Feedback) = check("feedback.$itemID.${feedback.rawValue}")

    companion object {
        fun unimplemented(): APIClientProtocol = Proxy.newProxyInstance(
            APIClientProtocol::class.java.classLoader,
            arrayOf(APIClientProtocol::class.java),
        ) { _, method, _ -> throw NotImplementedError("HomeFakeAPI: ${method.name}") } as APIClientProtocol
    }
}

object Fixtures {
    fun conversation(id: String, at: Instant, title: String = "Conversation $id", starred: Boolean = false, minutes: Long = 10) = Conversation(
        id = id, title = title, overview = "", emoji = "💬", category = null, createdAt = at, startedAt = at,
        finishedAt = at.plusSeconds(minutes * 60), status = Conversation.Status.Completed, isStarred = starred, actionItemCount = 0,
    )

    fun task(
        id: String,
        description: String,
        due: Instant? = null,
        created: Instant? = null,
        conversation: String? = null,
        owner: ActionItem.Owner = ActionItem.Owner.User,
        completed: Boolean = false,
    ) = ActionItem(
        id = id, description = description, isCompleted = completed, dueAt = due, conversationID = conversation,
        owner = owner, workstreamID = null, createdAt = created,
    )
}
