import { ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { getFirebaseStorage } from '@/lib/firebase/client';

/**
 * Upload an image to Firebase Storage
 * @param file - The file to upload
 * @param folder - The folder path in storage (e.g., 'announcements')
 * @returns The download URL of the uploaded file
 */
export async function uploadImage(file: File, folder: string = 'announcements'): Promise<string> {
  const timestamp = Date.now();
  const safeName = file.name.replace(/[^a-zA-Z0-9.-]/g, '_');
  const path = `${folder}/${timestamp}_${safeName}`;
  
  const storageRef = ref(getFirebaseStorage(), path);
  
  const snapshot = await uploadBytes(storageRef, file);
  const downloadURL = await getDownloadURL(snapshot.ref);
  
  return downloadURL;
}

/**
 * Validate that a file is an image
 */
export function isValidImage(file: File): boolean {
  const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
  return validTypes.includes(file.type);
}

/**
 * Validate file size (default max 5MB)
 */
export function isValidFileSize(file: File, maxSizeMB: number = 5): boolean {
  return file.size <= maxSizeMB * 1024 * 1024;
}
