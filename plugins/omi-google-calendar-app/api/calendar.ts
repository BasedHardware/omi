import axios, { AxiosError } from 'axios';
import { logger } from '../utils/logger';

export async function calendar_api_request(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  url: string,
  data?: any,
  headers?: Record<string, string>
): Promise<any> {
  try {
    const response = await axios({
      method,
      url,
      data,
      headers,
    });
    return response.data;
  } catch (e) {
    // Log the full error for debugging but do not expose it to the caller
    logger.error('Google Calendar API request failed', {
      method,
      url,
      error: e instanceof Error ? e.message : String(e),
    });

    // Return a generic error object
    return { error: 'Google Calendar API request failed' };
  }
}
