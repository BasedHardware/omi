import axios from 'axios';
import { ChatToolResponse } from '../types';
import { sanitizeErrorMessage } from '../utils/sanitizeError';

const CROSSREF_API_URL = 'https://api.crossref.org';

/**
 * Search Crossref works by a free‑text query.
 */
export async function searchCrossrefWorks(query: string): Promise<ChatToolResponse> {
  try {
    const response = await axios.get(`${CROSSREF_API_URL}/works`, {
      params: { query },
    });
    return ChatToolResponse.success(response.data);
  } catch (exc) {
    const sanitized = sanitizeErrorMessage(exc);
    return ChatToolResponse.error(`Error searching Crossref works: ${sanitized}`);
  }
}

/**
 * Retrieve a single Crossref work by DOI.
 */
export async function getCrossrefWork(doi: string): Promise<ChatToolResponse> {
  try {
    const response = await axios.get(`${CROSSREF_API_URL}/works/${doi}`);
    return ChatToolResponse.success(response.data);
  } catch (exc) {
    const sanitized = sanitizeErrorMessage(exc);
    return ChatToolResponse.error(`Error getting Crossref work: ${sanitized}`);
  }
}

/**
 * Retrieve Crossref works for a given author name.
 */
export async function getCrossrefWorksByAuthor(author: string): Promise<ChatToolResponse> {
  try {
    const response = await axios.get(`${CROSSREF_API_URL}/works`, {
      params: { author },
    });
    return ChatToolResponse.success(response.data);
  } catch (exc) {
    const sanitized = sanitizeErrorMessage(exc);
    return ChatToolResponse.error(`Error getting Crossref works by author: ${sanitized}`);
  }
}
