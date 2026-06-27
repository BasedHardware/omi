import * as admin from 'firebase-admin';

function ensureInitialized() {
  if (admin.apps.length) return;

  if (!process.env.FIREBASE_PROJECT_ID ||
      !process.env.FIREBASE_CLIENT_EMAIL ||
      !process.env.FIREBASE_PRIVATE_KEY) {
    throw new Error('Missing Firebase Admin SDK configuration environment variables!');
  }

  const privateKey = process.env.FIREBASE_PRIVATE_KEY.replace(/\\n/g, '\n');

  try {
    admin.initializeApp({
      credential: admin.credential.cert({
        projectId: process.env.FIREBASE_PROJECT_ID,
        clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
        privateKey: privateKey,
      }),
    });
    console.log('Firebase Admin SDK initialized successfully.');
  } catch (error: any) {
    console.error('Firebase Admin SDK initialization error:', error.stack);
    throw error;
  }
}

export function getDb() {
  ensureInitialized();
  return admin.firestore();
}

export function getAdminAuth() {
  ensureInitialized();
  return admin.auth();
}

export const verifyFirebaseToken = async (token: string) => {
  ensureInitialized();
  try {
    const decodedToken = await admin.auth().verifyIdToken(token);
    return decodedToken;
  } catch (error) {
    console.error('Error verifying Firebase ID token:', error);
    return null;
  }
};

export default admin;
