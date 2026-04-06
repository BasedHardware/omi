const OMI_API_BASE_URL = process.env.NEXT_PUBLIC_OMI_API_URL;
const OMI_API_SECRET_KEY_BASE = process.env.OMI_API_SECRET_KEY; // Base key from env

interface FetchOptions extends RequestInit {
  body?: any;
}

async function omiApiClient<T>(endpoint: string, uid: string, options: FetchOptions = {}): Promise<T> {
  if (!OMI_API_SECRET_KEY_BASE) {
    console.error('OMI_API_SECRET_KEY environment variable is not set.');
    throw new Error('API secret key base is missing. Cannot make API calls.');
  }
  if (!uid) {
     console.error('User UID is missing for Omi API call.');
    throw new Error('User UID is required for API calls.');
  }

  // Combine base secret and UID for the header value
  const combinedSecret = OMI_API_SECRET_KEY_BASE + uid;

  const url = `${OMI_API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    'secret-key': OMI_API_SECRET_KEY_BASE,
    'Authorization': `Bearer ${combinedSecret}`,
    ...options.headers,
  };

  const config: RequestInit = {
    ...options,
    headers,
  };

  // Stringify body if it exists and content type is JSON
  if (options.body && headers['Content-Type'] === 'application/json') {
    config.body = JSON.stringify(options.body);
  }

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      // Attempt to parse error details from the response body
      let errorData;
      try {
        errorData = await response.json();
      } catch (e) {
        // Ignore if response body is not JSON
      }
      console.error(`Omi API Error: ${response.status} ${response.statusText}`, errorData);
      throw new OmiApiError(`API request failed: ${response.status} ${response.statusText}`, response.status, errorData);
    }

    // Handle cases where the response might be empty (e.g., 204 No Content)
    if (response.status === 204) {
      return undefined as T; // Or handle as appropriate for your expected return types
    }

    return await response.json() as T;
  } catch (error) {
    console.error('Network or other error during Omi API call:', error);
    // Re-throw the error or handle it, potentially wrapping it
    if (error instanceof OmiApiError) {
        throw error;
    }
    throw new Error(`Failed to fetch from Omi API: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export default omiApiClient;

// Define and export the custom error class here
export class OmiApiError extends Error {
  status: number;
  details?: any;

  constructor(message: string, status: number, details?: any) {
    super(message);
    this.name = 'OmiApiError';
    this.status = status;
    this.details = details;
  }
} 