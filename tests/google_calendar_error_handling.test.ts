import request from 'supertest';
import express from 'express';
import authRouter from '../plugins/omi-google-calendar-app/routes/auth';
import callbackRouter from '../plugins/omi-google-calendar-app/routes/callback';
import * as calendarApi from '../plugins/omi-google-calendar-app/api/calendar';
import * as listEvents from '../plugins/omi-google-calendar-app/tools/list_events';
import * as createEvent from '../plugins/omi-google-calendar-app/tools/create_event';
import * as getEvent from '../plugins/omi-google-calendar-app/tools/get_event';
import * as updateEvent from '../plugins/omi-google-calendar-app/tools/update_event';
import * as deleteEvent from '../plugins/omi-google-calendar-app/tools/delete_event';
import * as listCalendars from '../plugins/omi-google-calendar-app/tools/list_calendars';

jest.mock('../plugins/omi-google-calendar-app/api/calendar');
jest.mock('../plugins/omi-google-calendar-app/services/auth');
jest.mock('../plugins/omi-google-calendar-app/services/callback');

const app = express();
app.use(authRouter);
app.use(callbackRouter);

describe('Google Calendar App error handling', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('auth endpoint does not leak exception text', async () => {
    const mockStartAuthFlow = jest.fn().mockRejectedValue(new Error('DB failure'));
    jest.spyOn(require('../plugins/omi-google-calendar-app/services/auth'), 'startAuthFlow').mockImplementation(mockStartAuthFlow);

    const res = await request(app).get('/auth/google');
    expect(res.status).toBe(500);
    expect(res.text).toBe('An unexpected error occurred while starting authentication.');
  });

  test('callback endpoint does not leak exception text', async () => {
    const mockHandleCallback = jest.fn().mockRejectedValue(new Error('Token exchange error'));
    jest.spyOn(require('../plugins/omi-google-calendar-app/services/callback'), 'handleAuthCallback').mockImplementation(mockHandleCallback);

    const res = await request(app).get('/auth/google/callback');
    expect(res.status).toBe(500);
    // The error card is a static file; we just check that it was served
    expect(res.header['content-type']).toMatch(/html/);
  });

  test('calendar_api_request returns generic error', async () => {
    jest.spyOn(calendarApi, 'calendar_api_request').mockImplementation(async () => {
      throw new Error('Network failure');
    });

    const res = await calendarApi.calendar_api_request('GET', '/events');
    expect(res).toEqual({ error: 'Google Calendar API request failed' });
  });

  test('list_events tool does not leak exception text', async () => {
    jest.spyOn(calendarApi, 'calendar_api_request').mockRejectedValue(new Error('API timeout'));
    const res = await listEvents.list_events_tool();
    expect(res.error).toContain('Failed to list events');
    expect(res.error).not.toContain('API timeout');
  });

  test('create_event tool does not leak exception text', async () => {
    jest.spyOn(calendarApi, 'calendar_api_request').mockRejectedValue(new Error('Invalid payload'));
    const res = await createEvent.create_event_tool({ title: 'Test' });
    expect(res.error).toContain('Failed to create event');
    expect(res.error).not.toContain('Invalid payload');
  });

  test('get_event tool does not leak exception text', async () => {
    jest.spyOn(calendarApi, 'calendar_api_request').mockRejectedValue(new Error('Not found'));
    const res = await getEvent.get_event_tool('123');
    expect(res.error).toContain('Failed to get event');
    expect(res.error).not.toContain('Not found');
  });

  test('update_event tool does not leak exception text', async () => {
    jest.spyOn(calendarApi, 'calendar_api_request').mockRejectedValue(new Error('Permission denied'));
    const res = await updateEvent.update_event_tool('123', { title: 'Updated' });
    expect(res.error).toContain('Failed to update event');
    expect(res.error).not.toContain('Permission denied');
  });

  test('delete_event tool does not leak exception text', async () => {
    jest.spyOn(calendarApi, 'calendar_api_request').mockRejectedValue(new Error('Delete error'));
    const res = await deleteEvent.delete_event_tool('123');
    expect(res.error).toContain('Failed to delete event');
    expect(res.error).not.toContain('Delete error');
  });

  test('list_calendars tool does not leak exception text', async () => {
    jest.spyOn(calendarApi, 'calendar_api_request').mockRejectedValue(new Error('Calendar list error'));
    const res = await listCalendars.list_calendars_tool();
    expect(res.error).toContain('Failed to list calendars');
    expect(res.error).not.toContain('Calendar list error');
  });
});
