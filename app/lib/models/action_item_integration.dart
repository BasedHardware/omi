enum ActionItemIntegration {
  appleReminders('Apple Reminders', 'apple-reminders-logo.png', false, null),
  appleCalendar('Apple Calendar', 'apple-calendar-logo.png', false, null);

  const ActionItemIntegration(this.title, this.imagePath, this.available, this.notAvailableText);

  final String title;
  final String imagePath;
  final bool available;
  final String? notAvailableText;
}