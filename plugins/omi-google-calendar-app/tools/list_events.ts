import { ChatToolResponse } from '../types';
import { calendar_api_request } from '../api/calendar';
import { logger } from '../utils/logger';

export async function list_events_tool(): Promise<ChatToolResponse> {
  try {
    const data = await calendar_api_request('GET', '/events');
    return { result: data };
  } catch (e) {
    logger.error('Failed to list events', {
      error: e instanceof Error ? e.message : String(e),
    });
    return { error: 'Failed to list events: an unexpected error occurred.' };
  }
}
