import {taskExportCopy} from './desktopReadClient';

test('names Flutter ActionItemsPage empty GET export_platform', () => {
  expect(taskExportCopy(true, 'todoist')).toBe('Exported to Todoist');
  expect(taskExportCopy(true, 'asana')).toBe('Exported to Asana');
  expect(taskExportCopy(true, 'google_tasks')).toBe('Exported to Google Tasks');
  expect(taskExportCopy(true, 'clickup')).toBe('Exported to ClickUp');
  expect(taskExportCopy(true, 'apple_reminders')).toBe('Exported to Reminders');
  expect(taskExportCopy(true, 'linear')).toBe('Exported to linear');
  expect(taskExportCopy(true, ' \u0085 ')).toBe('Exported to  \u0085 ');
  expect(taskExportCopy(true, '')).toBe('Exported to ');
  expect(taskExportCopy(true, null)).toBeNull();
  expect(taskExportCopy(true, undefined)).toBeNull();
  expect(taskExportCopy(false, 'todoist')).toBeNull();
  expect(taskExportCopy(undefined, 'todoist')).toBeNull();
});

test('names Flutter ActionItemsPage padded GET export_platform', () => {
  expect(taskExportCopy(true, '  todoist  ')).toBe('Exported to   todoist  ');
  expect(taskExportCopy(true, 'todoist ')).toBe('Exported to todoist ');
  expect(taskExportCopy(true, '\u0085todoist')).toBe('Exported to \u0085todoist');
  expect(taskExportCopy(true, '  asana  ')).toBe('Exported to   asana  ');
  expect(taskExportCopy(true, 'todoist')).toBe('Exported to Todoist');
});
