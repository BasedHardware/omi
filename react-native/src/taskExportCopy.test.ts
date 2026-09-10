import {taskExportCopy} from './desktopReadClient';

test('names GET exported platforms and omits missing or empty values', () => {
  expect(taskExportCopy(true, 'todoist')).toBe('Exported to Todoist');
  expect(taskExportCopy(true, 'asana')).toBe('Exported to Asana');
  expect(taskExportCopy(true, 'google_tasks')).toBe('Exported to Google Tasks');
  expect(taskExportCopy(true, 'clickup')).toBe('Exported to ClickUp');
  expect(taskExportCopy(true, 'apple_reminders')).toBe('Exported to Reminders');
  expect(taskExportCopy(true, 'linear')).toBe('Exported to linear');
  expect(taskExportCopy(true, ' \u0085 ')).toBeNull();
  expect(taskExportCopy(true, '')).toBeNull();
  expect(taskExportCopy(true, null)).toBeNull();
  expect(taskExportCopy(false, 'todoist')).toBeNull();
  expect(taskExportCopy(undefined, 'todoist')).toBeNull();
});
