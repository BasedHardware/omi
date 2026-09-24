import { ChatToolResponse } from '../types';
import { calendar_api_request } from '../api/calendar';
import { logger } from '../utils/logger';

export async function list_calendars_tool(): Promise<ChatToolResponse> {
  try {
    const data = await calendar_api_request('GET', '/calendars');
    return { result: data };
  } catch (e) {
    logger.error('Failed to list calendars', {
      error: e instanceof Error ? e.message : String(e),
    });
    return { error: 'Failed to list calendars: an unexpected error occurred.' };
  }
}
