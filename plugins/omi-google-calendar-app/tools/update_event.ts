import { ChatToolResponse } from '../types';
import { calendar_api_request } from '../api/calendar';
import { logger } from '../utils/logger';

export async function update_event_tool(eventId: string, updateData: any): Promise<ChatToolResponse> {
  try {
    const data = await calendar_api_request('PUT', `/events/${eventId}`, updateData);
    return { result: data };
  } catch (e) {
    logger.error('Failed to update event', {
      error: e instanceof Error ? e.message : String(e),
    });
    return { error: 'Failed to update event: an unexpected error occurred.' };
  }
}
