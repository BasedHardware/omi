import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';

// Ensure these environment variables are set in your .env.local or deployment environment
const TYPESENSE_HOST = process.env.TYPESENSE_HOST;
const TYPESENSE_API_KEY = process.env.TYPESENSE_API_KEY;
// Default collection name, can be overridden by an env var if needed
const COLLECTION_NAME = process.env.TYPESENSE_CONVERSATION_COLLECTION || 'conversations'; 

interface TypesenseCollectionResponse {
  name: string;
  num_documents: number;
  // other fields might exist but are not needed here
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  if (!TYPESENSE_HOST || !TYPESENSE_API_KEY) {
    console.error('TYPESENSE_HOST or TYPESENSE_API_KEY environment variables are not set.');
    return NextResponse.json({ totalConversations: 0, unavailable: true });
  }

  const typesenseUrl = TYPESENSE_HOST!.startsWith('https://') || TYPESENSE_HOST!.startsWith('http://')
    ? `${TYPESENSE_HOST}/collections/${COLLECTION_NAME}`
    : `https://${TYPESENSE_HOST}/collections/${COLLECTION_NAME}`;

  try {
    const response = await fetch(typesenseUrl, {
      method: 'GET',
      headers: {
        'X-TYPESENSE-API-KEY': TYPESENSE_API_KEY,
        'Accept': 'application/json',
      },
      // Consider adding a timeout if needed
      // signal: AbortSignal.timeout(5000) // Example: 5 second timeout
    });

    if (!response.ok) {
      let errorBody = '';
      try {
        errorBody = await response.text(); // Read body as text first
        console.error(`Typesense API error body: ${errorBody}`);
        const errorJson = JSON.parse(errorBody); // Try parsing as JSON
        errorBody = errorJson.message || errorBody;
      } catch (e) { 
         console.error('Could not parse Typesense error response as JSON.');
      }
      const errorMsg = `Typesense API request failed: ${response.status} ${response.statusText}. ${errorBody}`;
      console.error(errorMsg);
      // Use NextResponse for App Router
      return NextResponse.json(
          { message: 'Failed to communicate with Typesense.' }, 
          { status: response.status || 500 }
      );
    }

    const data: TypesenseCollectionResponse = await response.json();
    
    if (typeof data.num_documents !== 'number') {
        console.error('Typesense response missing or invalid num_documents field:', data);
        // Use NextResponse for App Router
        return NextResponse.json(
            { message: 'Invalid response format from Typesense.' }, 
            { status: 500 }
        );
    }

    const totalConversations = data.num_documents;

    // Optional: Add cache headers if the count doesn't change frequently
    // Example: return NextResponse.json({ totalConversations }, { headers: { 'Cache-Control': 's-maxage=3600' } });

    // Use NextResponse for App Router
    return NextResponse.json({ totalConversations });

  } catch (error: unknown) {
      // Catch network errors or other unexpected issues
      console.error('Error fetching conversation count from Typesense:', error);
      const message = error instanceof Error ? error.message : 'An unknown error occurred';
      // Use NextResponse for App Router
      return NextResponse.json(
          { message: `Failed to fetch conversation count: ${message}` }, 
          { status: 500 }
      );
  }
}

// Optional: You can define other methods like POST, PUT, DELETE as needed
// export async function POST(request: Request) { ... }
