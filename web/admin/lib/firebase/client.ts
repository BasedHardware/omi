import { initializeApp, getApps, getApp, type FirebaseApp } from 'firebase/app';
import { getAuth, type Auth } from 'firebase/auth';
import { getFirestore, type Firestore } from 'firebase/firestore';
import { getFunctions, type Functions } from 'firebase/functions';
import { getStorage, type FirebaseStorage } from 'firebase/storage';

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// Lazy initialization to avoid build-time failures when env vars are not set
let _app: FirebaseApp | null = null;
let _auth: Auth | null = null;
let _db: Firestore | null = null;
let _functions: Functions | null = null;
let _storage: FirebaseStorage | null = null;

function getFirebaseApp(): FirebaseApp {
  if (!_app) {
    _app = !getApps().length ? initializeApp(firebaseConfig) : getApp();
  }
  return _app;
}

// Use Object.defineProperty for lazy getters that maintain the same export API
const app = new Proxy({} as FirebaseApp, {
  get(_, prop) { return (getFirebaseApp() as any)[prop]; },
});

const auth = new Proxy({} as Auth, {
  get(_, prop) {
    if (!_auth) _auth = getAuth(getFirebaseApp());
    return (_auth as any)[prop];
  },
});

const db = new Proxy({} as Firestore, {
  get(_, prop) {
    if (!_db) _db = getFirestore(getFirebaseApp());
    return (_db as any)[prop];
  },
});

const functions = new Proxy({} as Functions, {
  get(_, prop) {
    if (!_functions) _functions = getFunctions(getFirebaseApp());
    return (_functions as any)[prop];
  },
});

const storage = new Proxy({} as FirebaseStorage, {
  get(_, prop) {
    if (!_storage) _storage = getStorage(getFirebaseApp());
    return (_storage as any)[prop];
  },
});

export { app, auth, db, functions, storage }; 