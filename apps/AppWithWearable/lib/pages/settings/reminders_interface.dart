abstract class RemindersInterface {
  void addReminder(String title, DateTime dueDate,
      [Duration duration = const Duration(hours: 1)]);
}
