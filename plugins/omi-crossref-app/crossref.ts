/**
 * Crossref API wrapper used by the omi-crossref-app plugin.
 *
 * All public functions return a `ChatToolResponse` which contains either
 * a `data` field or an `error` field.  Errors are sanitized using
 * `sanitizeError` to avoid leaking raw exception details.
 */

import axios from 'axios';
import { sanitizeError } from './sanitize';

export interface ChatToolResponse {
  data?: any;
  error?: string;
}

/**
 * Search Crossref works by a free‑text query.
 *
 * @param query - The search string.
 * @returns A promise resolving to a `ChatToolResponse`.
 */
export async function search_crossref_works(query: string): Promise<ChatToolResponse> {
  try {
    const resp = await axios.get('https://api.crossref.org/works', {
      params: { query },
    });
    return { data: resp.data };
  } catch (e) {
    return { error: sanitizeError(e) };
  }
}

/**
 * Retrieve a single Crossref work by DOI.
 *
 * @param doi - The DOI of the work.
 * @returns A promise resolving to a `ChatToolResponse`.
 */
export async function get_crossref_work(doi: string): Promise<ChatToolResponse> {
  try {
    const resp = await axios.get(`https://api.crossref.org/works/${doi}`);
    return { data: resp.data };
  } catch (e) {
    return { error: sanitizeError(e) };
  }
}

/**
 * Retrieve Crossref works by author name.
 *
 * @param author - The author's name.
 * @returns A promise resolving to a `ChatToolResponse`.
 */
export async function get_crossref_works_by_author(author: string): Promise<ChatToolResponse> {
  try {
    const resp = await axios.get('https://api.crossref.org/works', {
      params: { author },
    });
    return { data: resp.data };
  } catch (e) {
    return { error: sanitizeError(e) };
  }
}
