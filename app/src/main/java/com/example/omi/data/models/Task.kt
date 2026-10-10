```kotlin
@Entity(tableName = "tasks")
data class Task(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    val title: String,
    val description: String? = null,
    val isCompleted: Boolean = false,
    val createdAt: Long = System.currentTimeMillis(),
    val parentTaskId: Int? = null, // Novo campo para vincular sub-tarefas
    val indentationLevel: Int = 0 // Campo para controlar o nível de recuo visual
)
