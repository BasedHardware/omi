package com.friend.ios.service.stores

/**
 * The task list as the chat sees it (iOS sets `chat.tasks = tasks`, `TasksStore` itself): what the
 * agent added or ticked off shows as cards under its answers, and Undo goes back through the store.
 */
fun TasksStore.asChatTasks(): ChatTasks = TasksStoreChatTasks(this)

private class TasksStoreChatTasks(private val store: TasksStore) : ChatTasks {
    override val tasks: List<ChatTasks.Task>
        get() = store.tasks.map { ChatTasks.Task(it.id, it.description, it.isCompleted) }

    override val lastError: String? get() = store.lastError

    override suspend fun load() = store.load()

    override suspend fun delete(id: String) = store.delete(id)

    override suspend fun setCompleted(id: String, completed: Boolean) = store.setCompleted(id, completed)
}
