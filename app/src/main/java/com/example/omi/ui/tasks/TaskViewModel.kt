```kotlin
class TaskViewModel(application: Application) : AndroidViewModel(application) {
    private val taskDao = OmiDatabase.getDatabase(application).taskDao()

    val allTasks: Flow<List<Task>> = taskDao.getAllTasks()

    // Função para adicionar uma nova tarefa
    fun addTask(title: String, description: String?, parentTaskId: Int? = null, indentationLevel: Int = 0) {
        viewModelScope.launch {
            val task = Task(
                title = title,
                description = description,
                parentTaskId = parentTaskId,
                indentationLevel = indentationLevel
            )
            taskDao.insert(task)
        }
    }

    // Função para atualizar uma tarefa
    fun updateTask(task: Task) {
        viewModelScope.launch {
            taskDao.update(task)
        }
    }

    // Função para mover uma tarefa (e suas sub-tarefas) para um novo pai
    fun moveTask(taskId: Int, newParentId: Int?) {
        viewModelScope.launch {
            taskDao.moveTaskWithSubTasks(taskId, newParentId)
        }
    }

    // Função para obter todas as tarefas com hierarquia
    fun getTasksWithHierarchy(): Flow<List<TaskWithSubTasks>> {
        return taskDao.getAllParentTasks().map { parentTasks ->
            parentTasks.map { parent ->
                TaskDao.TaskWithSubTasks(
                    task = parent,
                    subTasks = taskDao.getSubTasks(parent.id).first()
                )
            }
        }
    }
}
