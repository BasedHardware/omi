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

// Lazy initialization via getter functions.
// Proxies break Firebase SDK's instanceof checks in doc()/getDoc()/onAuthStateChanged(),
// so we return real instances directly.
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

function getFirebaseAuth(): Auth {
  if (!_auth) _auth = getAuth(getFirebaseApp());
  return _auth;
}

function getFirebaseDb(): Firestore {
  if (!_db) _db = getFirestore(getFirebaseApp());
  return _db;
}

function getFirebaseFunctions(): Functions {
  if (!_functions) _functions = getFunctions(getFirebaseApp());
  return _functions;
}

function getFirebaseStorage(): FirebaseStorage {
  if (!_storage) _storage = getStorage(getFirebaseApp());
  return _storage;
}

export {
  getFirebaseApp,
  getFirebaseAuth,
  getFirebaseDb,
  getFirebaseFunctions,
  getFirebaseStorage,
}; 