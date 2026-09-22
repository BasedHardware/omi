import axios from 'axios';
import { ChatToolResponse } from './types';
import { sanitizeError } from './utils';

/**
 * Search Crossref works by query string.
 *
 * @param query - The search query.
 * @returns A ChatToolResponse containing either the result or an error.
 */
export async function search_crossref_works(query: string): Promise<ChatToolResponse> {
  try {
    const response = await axios.get('https://api.crossref.org/works', {
      params: { query },
    });
    return { result: response.data };
  } catch (e) {
    return { error: sanitizeError(e) };
  }
}

/**
 * Get a single Crossref work by DOI.
 *
 * @param doi - The DOI of the work.
 * @returns A ChatToolResponse containing either the result or an error.
 */
export async function get_crossref_work(doi: string): Promise<ChatToolResponse> {
  try {
    const response = await axios.get(`https://api.crossref.org/works/${encodeURIComponent(doi)}`);
    return { result: response.data };
  } catch (e) {
    return { error: sanitizeError(e) };
  }
}

/**
 * Get Crossref works by author name.
 *
 * @param author - The author's name.
 * @returns A ChatToolResponse containing either the result or an error.
 */
export async function get_crossref_works_by_author(author: string): Promise<ChatToolResponse> {
  try {
    const response = await axios.get('https://api.crossref.org/works', {
      params: { 'query.author': author },
    });
    return { result: response.data };
  } catch (e) {
    return { error: sanitizeError(e) };
  }
}
