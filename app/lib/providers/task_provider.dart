import 'package:flutter/foundation.dart';
import '../models/task.dart';
import '../services/task_service.dart';

class TaskProvider extends ChangeNotifier {
  final TaskService _taskService = TaskService();
  List<Task> _tasks = [];
  bool _isLoading = false;

  List<Task> get tasks => _tasks;
  bool get isLoading => _isLoading;

  Future<void> loadTasks() async {
    _isLoading = true;
    notifyListeners();
    
    try {
      _tasks = await _taskService.getAllTasks();
    } catch (e) {
      debugPrint('Error loading tasks: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> toggleTaskComplete(String taskId, bool completed) async {
    try {
      await _taskService.updateTaskCompletion(taskId, completed);
      
      final taskIndex = _tasks.indexWhere((task) => task.id == taskId);
      if (taskIndex != -1) {
        _tasks[taskIndex] = _tasks[taskIndex].copyWith(completed: completed);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error toggling task completion: $e');
    }
  }

  /// Indents a task to make it a subtask of the task above it
  /// This mirrors the macOS Tab behavior for task indentation
  Future<void> indentTask(String taskId, int currentIndex) async {
    if (currentIndex == 0) return; // Cannot indent first task

    try {
      final currentTask = _tasks[currentIndex];
      final parentTask = _tasks[currentIndex - 1];
      
      // Calculate new depth (one level deeper than parent)
      final newDepth = (parentTask.depth ?? 0) + 1;
      
      // Update the task with new parent and depth
      final updatedTask = currentTask.copyWith(
        parentId: parentTask.id,
        depth: newDepth,
      );
      
      // Update in service/backend
      await _taskService.updateTaskHierarchy(
        taskId: taskId,
        parentId: parentTask.id,
        depth: newDepth,
      );
      
      // Update local state
      _tasks[currentIndex] = updatedTask;
      
      // Resort tasks to maintain hierarchy order
      _sortTasksByHierarchy();
      
      notifyListeners();
    } catch (e) {
      debugPrint('Error indenting task: $e');
      rethrow;
    }
  }

  /// Sorts tasks to maintain proper hierarchical display order
  void _sortTasksByHierarchy() {
    _tasks.sort((a, b) {
      // First sort by parent hierarchy, then by original order
      if (a.parentId == b.parentId) {
        return (a.order ?? 0).compareTo(b.order ?? 0);
      }
      
      // If one is parent of another, parent comes first
      if (a.id == b.parentId) return -1;
      if (b.id == a.parentId) return 1;
      
      // Otherwise maintain creation order
      return (a.createdAt ?? DateTime.now())
          .compareTo(b.createdAt ?? DateTime.now());
    });
  }

  Future<void> createTask(Task task) async {
    try {
      final createdTask = await _taskService.createTask(task);
      _tasks.add(createdTask);
      _sortTasksByHierarchy();
      notifyListeners();
    } catch (e) {
      debugPrint('Error creating task: $e');
      rethrow;
    }
  }

  Future<void> updateTask(Task task) async {
    try {
      await _taskService.updateTask(task);
      
      final index = _tasks.indexWhere((t) => t.id == task.id);
      if (index != -1) {
        _tasks[index] = task;
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error updating task: $e');
      rethrow;
    }
  }

  Future<void> deleteTask(String taskId) async {
    try {
      await _taskService.deleteTask(taskId);
      _tasks.removeWhere((task) => task.id == taskId);
      notifyListeners();
    } catch (e) {
      debugPrint('Error deleting task: $e');
      rethrow;
    }
  }
}
