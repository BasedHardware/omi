```kotlin
@Composable
fun TaskListScreen(viewModel: TaskViewModel) {
    val tasksWithHierarchy by viewModel.getTasksWithHierarchy().collectAsState(initial = emptyList())

    LazyColumn {
        items(tasksWithHierarchy) { taskWithSubTasks ->
            TaskItem(
                task = taskWithSubTasks.task,
                onTaskUpdated = { updatedTask ->
                    viewModel.updateTask(updatedTask)
                },
                onMoveTask = { taskId, newParentId ->
                    viewModel.moveTask(taskId, newParentId)
                },
                indentationLevel = 0
            )

            // Exibir sub-tarefas
            taskWithSubTasks.subTasks.forEach { subTask ->
                TaskItem(
                    task = subTask,
                    onTaskUpdated = { updatedTask ->
                        viewModel.updateTask(updatedTask)
                    },
                    onMoveTask = { taskId, newParentId ->
                        viewModel.moveTask(taskId, newParentId)
                    },
                    indentationLevel = 1
                )
            }
        }
    }
}

@Composable
fun TaskItem(
    task: Task,
    onTaskUpdated: (Task) -> Unit,
    onMoveTask: (Int, Int?) -> Unit,
    indentationLevel: Int
) {
    var isExpanded by remember { mutableStateOf(false) }
    var editedTitle by remember { mutableStateOf(task.title) }
    var editedDescription by remember { mutableStateOf(task.description ?: "") }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = (16 * indentationLevel).dp)
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth()
        ) {
            Checkbox(
                checked = task.isCompleted,
                onCheckedChange = { isChecked ->
                    onTaskUpdated(task.copy(isCompleted = isChecked))
                }
            )

            TextField(
                value = editedTitle,
                onValueChange = { editedTitle = it },
                modifier = Modifier.weight(1f),
                onDismissRequest = {
                    onTaskUpdated(task.copy(title = editedTitle, description = editedDescription))
                }
            )

            IconButton(onClick = { isExpanded = !isExpanded }) {
                Icon(Icons.Default.ExpandMore, contentDescription = "Expand")
            }
        }

        if (isExpanded) {
            TextField(
                value = editedDescription,
                onValueChange = { editedDescription = it },
                modifier = Modifier.fillMaxWidth(),
                onDismissRequest = {
                    onTaskUpdated(task.copy(title = editedTitle, description = editedDescription))
                }
            )

            Button(onClick = {
                onTaskUpdated(task.copy(title = editedTitle, description = editedDescription))
            }) {
                Text("Save")
            }
        }
    }
}
