import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/task.dart';
import '../config/api_config.dart';

class TaskService {
  final String _baseUrl = ApiConfig.baseUrl;
  final Duration _timeout = const Duration(seconds: 30);

  Future<List<Task>> getAllTasks() async {
    try {
      final response = await http
          .get(
            Uri.parse('$_baseUrl/tasks'),
            headers: {'Content-Type': 'application/json'},
          )
          .timeout(_timeout);

      if (response.statusCode == 200) {
        final List<dynamic> jsonList = json.decode(response.body);
        return jsonList.map((json) => Task.fromJson(json)).toList();
      } else {
        throw Exception('Failed to load tasks: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Failed to load tasks: $e');
    }
  }

  Future<Task> createTask(Task task) async {
    try {
      final response = await http
          .post(
            Uri.parse('$_baseUrl/tasks'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode(task.toJson()),
          )
          .timeout(_timeout);

      if (response.statusCode == 201) {
        return Task.fromJson(json.decode(response.body));
      } else {
        throw Exception('Failed to create task: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Failed to create task: $e');
    }
  }

  Future<void> updateTask(Task task) async {
    try {
      final response = await http
          .put(
            Uri.parse('$_baseUrl/tasks/${task.id}'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode(task.toJson()),
          )
          .timeout(_timeout);

      if (response.statusCode != 200) {
        throw Exception('Failed to update task: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Failed to update task: $e');
    }
  }

  Future<void> updateTaskCompletion(String taskId, bool completed) async {
    try {
      final response = await http
          .patch(
            Uri.parse('$_baseUrl/tasks/$taskId/completion'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode({'completed': completed}),
          )
          .timeout(_timeout);

      if (response.statusCode != 200) {
        throw Exception('Failed to update task completion: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Failed to update task completion: $e');
    }
  }

  /// Updates task hierarchy (parentId and depth) - mirrors macOS indent logic
  Future<void> updateTaskHierarchy({
    required String taskId,
    required String parentId,
    required int depth,
  }) async {
    try {
      final response = await http
          .patch(
            Uri.parse('$_baseUrl/tasks/$taskId/hierarchy'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode({
              'parentId': parentId,
              'depth': depth,
            }),
          )
          .timeout(_timeout);

      if (response.statusCode != 200) {
        throw Exception('Failed to update task hierarchy: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Failed to update task hierarchy: $e');
    }
  }

  Future<void> deleteTask(String taskId) async {
    try {
      final response = await http
          .delete(Uri.parse('$_baseUrl/tasks/$taskId'))
          .timeout(_timeout);

      if (response.statusCode != 200 && response.statusCode != 204) {
        throw Exception('Failed to delete task: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Failed to delete task: $e');
    }
  }
}
