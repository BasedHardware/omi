import { ApiHttpError } from './api';

export function recapGenerationError(error: unknown): string {
  if (error instanceof ApiHttpError) {
    switch (error.status) {
      case 400:
        return 'No completed conversations are ready to summarize for this day. Finish syncing, then try again.';
      case 409:
        return 'This recap is already being generated. Try again shortly.';
      case 429:
        return 'Please wait a moment before generating this recap again.';
      case 422:
        return 'Choose a valid date that is not in the future.';
      case 401:
        return 'Please sign in again before generating a recap.';
      case 402:
        return 'Your plan’s summary limit has been reached. Check your plan before retrying.';
    }
  }
  return 'Couldn’t generate this recap. Check your connection and try again.';
}
