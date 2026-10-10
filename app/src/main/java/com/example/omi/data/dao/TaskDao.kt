```kotlin
@Dao
interface TaskDao {
    @Insert
    suspend fun insert(task: Task)

    @Update
    suspend fun update(task: Task)

    @Delete
    suspend fun delete(task: Task)

    @Query("SELECT * FROM tasks WHERE parentTaskId IS NULL ORDER BY createdAt")
    fun getAllParentTasks(): Flow<List<Task>>

    @Query("SELECT * FROM tasks WHERE parentTaskId = :parentId ORDER BY createdAt")
    fun getSubTasks(parentId: Int): Flow<List<Task>>

    @Query("SELECT * FROM tasks ORDER BY createdAt")
    fun getAllTasks(): Flow<List<Task>>

    @Transaction
    @Query("SELECT * FROM tasks WHERE id = :taskId")
    suspend fun getTaskWithSubTasks(taskId: Int): TaskWithSubTasks?

    // Novo método para mover tarefas e suas sub-tarefas
    @Transaction
    suspend fun moveTaskWithSubTasks(taskId: Int, newParentId: Int?) {
        val task = getTask(taskId)
        if (task != null) {
            update(task.copy(parentTaskId = newParentId))
            if (newParentId != null) {
                // Atualizar o nível de recuo das sub-tarefas
                val subTasks = getSubTasks(taskId)
                subTasks.forEach { subTask ->
                    update(subTask.copy(
                        parentTaskId = newParentId,
                        indentationLevel = task.indentationLevel + 1
                    ))
                }
            }
        }
    }

    @Query("SELECT * FROM tasks WHERE id = :taskId")
    suspend fun getTask(taskId: Int): Task?

    // Classe para representar uma tarefa com suas sub-tarefas
    data class TaskWithSubTasks(
        @Embedded val task: Task,
        @Relation(
            parentColumn = "id",
            entityColumn = "parentTaskId"
        )
        val subTasks: List<Task>
    )
}
