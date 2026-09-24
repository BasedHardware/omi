import { ChatToolResponse } from '../types';
import { calendar_api_request } from '../api/calendar';
import { logger } from '../utils/logger';

export async function get_event_tool(eventId: string): Promise<ChatToolResponse> {
  try {
    const data = await calendar_api_request('GET', `/events/${eventId}`);
    return { result: data };
  } catch (e) {
    logger.error('Failed to get event', {
      error: e instanceof Error ? e.message : String(e),
    });
    return { error: 'Failed to get event: an unexpected error occurred.' };
  }
}
