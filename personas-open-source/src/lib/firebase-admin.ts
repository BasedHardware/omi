import * as admin from 'firebase-admin';

// Initialize the app only if it hasn't been initialized already
if (!admin.apps.length) {
  const privateKey = process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n');
  
  admin.initializeApp({
    credential: admin.credential.cert({
      projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
      privateKey,
    }),
  });
}

// Export the admin auth and firestore instances
export const auth = admin.auth();
export const db = admin.firestore();
export const firestore = admin.firestore; 