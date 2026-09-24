import { ChatToolResponse } from '../types';
import { calendar_api_request } from '../api/calendar';
import { logger } from '../utils/logger';

export async function create_event_tool(eventData: any): Promise<ChatToolResponse> {
  try {
    const data = await calendar_api_request('POST', '/events', eventData);
    return { result: data };
  } catch (e) {
    logger.error('Failed to create event', {
      error: e instanceof Error ? e.message : String(e),
    });
    return { error: 'Failed to create event: an unexpected error occurred.' };
  }
}
