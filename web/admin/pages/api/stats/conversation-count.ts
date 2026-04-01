import { NextApiRequest, NextApiResponse } from 'next';
import { verifyFirebaseToken, getDb } from '@/lib/firebase/admin';

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

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', ['GET']);
    return res.status(405).json({ message: 'Method Not Allowed' });
  }

  // Verify admin auth
  const authorization = req.headers.authorization;
  if (!authorization || !authorization.startsWith('Bearer ')) {
    return res.status(401).json({ message: 'Unauthorized: Missing or invalid token' });
  }
  const token = authorization.split('Bearer ')[1];
  const decodedToken = await verifyFirebaseToken(token);
  if (!decodedToken) {
    return res.status(401).json({ message: 'Unauthorized: Invalid token' });
  }
  const db = getDb();
  const adminDoc = await db.collection('adminData').doc(decodedToken.uid).get();
  if (!adminDoc.exists) {
    return res.status(403).json({ message: 'Forbidden: Not an admin' });
  }

  if (!TYPESENSE_HOST || !TYPESENSE_API_KEY) {
    console.error('TYPESENSE_HOST or TYPESENSE_API_KEY environment variables are not set.');
    return res.status(500).json({ message: 'Server configuration error: Typesense is not configured.' });
  }

  const typesenseUrl = `${TYPESENSE_HOST}/collections/${COLLECTION_NAME}`;

  try {
    const response = await fetch(typesenseUrl, {
      method: 'GET',
      headers: {
        'X-TYPESENSE-API-KEY': TYPESENSE_API_KEY,
        'Accept': 'application/json',
      },
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
      // Don't expose raw error messages to the client unless necessary
      return res.status(response.status || 500).json({ message: 'Failed to communicate with Typesense.' });
    }

    const data: TypesenseCollectionResponse = await response.json();
    
    if (typeof data.num_documents !== 'number') {
        console.error('Typesense response missing or invalid num_documents field:', data);
        return res.status(500).json({ message: 'Invalid response format from Typesense.' });
    }

    const totalConversations = data.num_documents;

    // Optional: Add cache headers if the count doesn't change frequently
    // res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate'); // Cache for 1 hour

    res.status(200).json({ totalConversations });

  } catch (error: unknown) {
      // Catch network errors or other unexpected issues
      console.error('Error fetching conversation count from Typesense:', error);
      const message = error instanceof Error ? error.message : 'An unknown error occurred';
      res.status(500).json({ message: `Failed to fetch conversation count: ${message}` });
  }
} 