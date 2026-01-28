import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:provider/provider.dart';
import 'package:omi/models/task.dart';
import 'package:omi/providers/task_provider.dart';
import 'package:omi/pages/chat/widgets/task_list_item.dart';

class MockTaskProvider extends Mock implements TaskProvider {}

void main() {
  group('TaskListItem Swipe to Subtask Tests', () {
    late MockTaskProvider mockTaskProvider;
    late Task testTask;
    late Task parentTask;

    setUp(() {
      mockTaskProvider = MockTaskProvider();
      testTask = const Task(
        id: 'task-2',
        title: 'Test Task',
        description: 'Test Description',
        completed: false,
      );
      parentTask = const Task(
        id: 'task-1',
        title: 'Parent Task',
        completed: false,
      );
    });

    Widget createTestWidget({
      required Task task,
      required int index,
    }) {
      return MaterialApp(
        home: Scaffold(
          body: ChangeNotifierProvider<TaskProvider>.value(
            value: mockTaskProvider,
            child: TaskListItem(
              task: task,
              index: index,
              onTap: () {},
              onCheckboxChanged: (value) {},
            ),
          ),
        ),
      );
    }

    testWidgets('should show swipe action for making subtask', (tester) async {
      await tester.pumpWidget(createTestWidget(task: testTask, index: 1));

      // Find the slidable widget
      final slidableFinder = find.byType(TaskListItem);
      expect(slidableFinder, findsOneWidget);

      // Swipe right to reveal the action
      await tester.drag(slidableFinder, const Offset(300, 0));
      await tester.pumpAndSettle();

      // Verify the subtask action is visible
      expect(find.text('Subtask'), findsOneWidget);
      expect(find.byIcon(Icons.subdirectory_arrow_right), findsOneWidget);
    });

    testWidgets('should call indentTask when swipe action is tapped', (tester) async {
      await tester.pumpWidget(createTestWidget(task: testTask, index: 1));

      // Swipe right to reveal actions
      await tester.drag(find.byType(TaskListItem), const Offset(300, 0));
      await tester.pumpAndSettle();

      // Tap the subtask action
      await tester.tap(find.text('Subtask'));
      await tester.pumpAndSettle();

      // Verify indentTask was called with correct parameters
      verify(mockTaskProvider.indentTask('task-2', 1)).called(1);
    });

    testWidgets('should show error message when trying to indent first task', (tester) async {
      await tester.pumpWidget(createTestWidget(task: testTask, index: 0));

      // Swipe right to reveal actions
      await tester.drag(find.byType(TaskListItem), const Offset(300, 0));
      await tester.pumpAndSettle();

      // Tap the subtask action
      await tester.tap(find.text('Subtask'));
      await tester.pumpAndSettle();

      // Verify error message is shown
      expect(find.text('Cannot create subtask: No parent task above'), findsOneWidget);
      
      // Verify indentTask was not called
      verifyNever(mockTaskProvider.indentTask(any, any));
    });

    testWidgets('should show success message after creating subtask', (tester) async {
      await tester.pumpWidget(createTestWidget(task: testTask, index: 1));

      // Swipe right to reveal actions
      await tester.drag(find.byType(TaskListItem), const Offset(300, 0));
      await tester.pumpAndSettle();

      // Tap the subtask action
      await tester.tap(find.text('Subtask'));
      await tester.pumpAndSettle();

      // Verify success message is shown
      expect(find.text('Task converted to subtask'), findsOneWidget);
    });

    testWidgets('should display task with correct indentation based on depth', (tester) async {
      final indentedTask = testTask.copyWith(depth: 2);
      
      await tester.pumpWidget(createTestWidget(task: indentedTask, index: 1));

      // Find the container with margin
      final containerFinder = find.descendant(
        of: find.byType(TaskListItem),
        matching: find.byType(Container),
      );

      final container = tester.widget<Container>(containerFinder.first);
      final margin = container.margin as EdgeInsets;
      
      // Verify left margin is correctly calculated (depth * 20)
      expect(margin.left, equals(40.0)); // depth 2 * 20
    });

    testWidgets('should show subtask indicator when task has subtasks', (tester) async {
      final taskWithSubtasks = testTask.copyWith(subtaskIds: ['subtask-1', 'subtask-2']);
      
      await tester.pumpWidget(createTestWidget(task: taskWithSubtasks, index: 1));

      // Verify arrow indicator is shown
      expect(find.byIcon(Icons.keyboard_arrow_right), findsOneWidget);
    });

    testWidgets('should not show subtask indicator when task has no subtasks', (tester) async {
      await tester.pumpWidget(createTestWidget(task: testTask, index: 1));

      // Verify no arrow indicator is shown
      expect(find.byIcon(Icons.keyboard_arrow_right), findsNothing);
    });
  });
}
