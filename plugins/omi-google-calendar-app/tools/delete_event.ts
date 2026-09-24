import { ChatToolResponse } from '../types';
import { calendar_api_request } from '../api/calendar';
import { logger } from '../utils/logger';

export async function delete_event_tool(eventId: string): Promise<ChatToolResponse> {
  try {
    await calendar_api_request('DELETE', `/events/${eventId}`);
    return { result: `Event ${eventId} deleted.` };
  } catch (e) {
    logger.error('Failed to delete event', {
      error: e instanceof Error ? e.message : String(e),
    });
    return { error: 'Failed to delete event: an unexpected error occurred.' };
  }
}
