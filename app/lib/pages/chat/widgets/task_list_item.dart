import 'package:flutter/material.dart';
import 'package:flutter_slidable/flutter_slidable.dart';
import 'package:provider/provider.dart';
import '../../../providers/task_provider.dart';
import '../../../models/task.dart';

class TaskListItem extends StatelessWidget {
  final Task task;
  final int index;
  final VoidCallback? onTap;
  final ValueChanged<bool?>? onCheckboxChanged;

  const TaskListItem({
    Key? key,
    required this.task,
    required this.index,
    this.onTap,
    this.onCheckboxChanged,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Slidable(
      key: ValueKey(task.id),
      startActionPane: ActionPane(
        motion: const DrawerMotion(),
        extentRatio: 0.3,
        children: [
          CustomSlidableAction(
            onPressed: (context) => _makeSubtask(context),
            backgroundColor: Theme.of(context).colorScheme.secondary,
            foregroundColor: Colors.white,
            icon: Icons.subdirectory_arrow_right,
            label: 'Subtask',
            borderRadius: BorderRadius.circular(8),
          ),
        ],
      ),
      child: Container(
        margin: EdgeInsets.only(
          left: (task.depth ?? 0) * 20.0,
          top: 4.0,
          bottom: 4.0,
          right: 8.0,
        ),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: Theme.of(context).dividerColor.withOpacity(0.2),
          ),
        ),
        child: ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          leading: Checkbox(
            value: task.completed,
            onChanged: onCheckboxChanged,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          title: Text(
            task.title,
            style: TextStyle(
              decoration: task.completed ? TextDecoration.lineThrough : null,
              color: task.completed 
                ? Theme.of(context).textTheme.bodyMedium?.color?.withOpacity(0.6)
                : null,
            ),
          ),
          subtitle: task.description?.isNotEmpty == true
            ? Text(
                task.description!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: Theme.of(context).textTheme.bodySmall?.color?.withOpacity(0.7),
                ),
              )
            : null,
          onTap: onTap,
          trailing: task.hasSubtasks 
            ? Icon(
                Icons.keyboard_arrow_right,
                color: Theme.of(context).iconTheme.color?.withOpacity(0.5),
              )
            : null,
        ),
      ),
    );
  }

  void _makeSubtask(BuildContext context) {
    final taskProvider = Provider.of<TaskProvider>(context, listen: false);
    
    // Check if this is the first item (index 0) - if so, do nothing
    if (index == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Cannot create subtask: No parent task above'),
          duration: Duration(seconds: 2),
        ),
      );
      return;
    }

    // Use the same logic as macOS Tab behavior
    taskProvider.indentTask(task.id, index);
    
    // Provide feedback to user
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Task converted to subtask'),
        duration: Duration(seconds: 1),
      ),
    );
  }
}
