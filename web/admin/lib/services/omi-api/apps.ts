import omiApiClient from './client';
import type { OmiApp, OmiAppInput } from './types';
import { getDb } from '@/lib/firebase/admin';

// Adjust endpoint paths based on actual API
const APPS_ENDPOINT = '/v1/apps';

/**
 * Fetches a list of all apps.
 * @param uid - The UID of the authenticated user.
 */
export async function getApps(uid: string): Promise<OmiApp[]> {
  const endpoint = `${APPS_ENDPOINT}`;
  return await omiApiClient<OmiApp[]>(endpoint, uid, { method: 'GET' });
}

/**
 * Fetches a single app by its ID.
 * @param uid - The UID of the authenticated user.
 */
export async function getAppById(uid: string, appId: string): Promise<OmiApp> {
  const endpoint = `${APPS_ENDPOINT}/${appId}`;
  return await omiApiClient<OmiApp>(endpoint, uid, { method: 'GET' });
}

/**
 * Creates a new app.
 * @param uid - The UID of the authenticated user.
 */
export async function createApp(uid: string, appData: OmiAppInput): Promise<OmiApp> {
  return await omiApiClient<OmiApp>(APPS_ENDPOINT, uid, {
    method: 'POST',
    body: appData,
  });
}

/**
 * Updates an existing app.
 * @param uid - The UID of the authenticated user.
 */
export async function updateApp(
  uid: string,
  appId: string,
  appData: Partial<OmiAppInput>
): Promise<OmiApp> {
   const endpoint = `${APPS_ENDPOINT}/${appId}`;
   return await omiApiClient<OmiApp>(endpoint, uid, {
    method: 'PATCH', // Or 'PUT' depending on API design
    body: appData,
  });
}

/**
 * Deletes an app by its ID.
 * @param uid - The UID of the authenticated user.
 */
export async function deleteApp(uid: string, appId: string): Promise<void> {
  const endpoint = `${APPS_ENDPOINT}/${appId}`;
  // Expecting a 204 No Content or similar on success
  await omiApiClient<void>(endpoint, uid, { method: 'DELETE' });
}

// Fetch all public unapproved apps
export const getUnapprovedApps = async (uid: string): Promise<OmiApp[]> => {
  // Assuming this endpoint exists in the Omi API
  // Pass a dummy/empty UID or adjust client if UID is mandatory but not used for this specific GET
  return omiApiClient<OmiApp[]>('/v1/apps/public/unapproved', uid, { method: 'GET' });
};

/**
 * Submits a review action (approve/reject) for an app.
 * @param uid - The UID of the authenticated admin user.
 * @param appId - The ID of the app to review.
 * @param action - The review action ('approve' or 'reject').
 * @param reason - Optional reason for rejection.
 */
export async function reviewApp(
  uid: string,
  appId: string,
  action: 'approve' | 'reject',
  reason?: string
): Promise<{ success: boolean; message?: string }> {
  const db = getDb();
  const appDocRef = db.collection('plugins_data').doc(appId);

  let dataToUpdate: {
    status: string;
    approved: boolean;
  };

  if (action === 'approve') {
    dataToUpdate = {
      status: 'approved',
      approved: true,
    };
  } else { // action === 'reject'
    dataToUpdate = {
      status: 'rejected',
      approved: false,
    };
  }

  try {
    await appDocRef.update(dataToUpdate);
     console.log(`App ${appId} status updated to ${action} by user ${uid}.`); // Optional: for server logs
    return { success: true };
  } catch (error: any) {
    console.error(`Error updating app ${appId} to ${action} by user ${uid}:`, error);
    return { success: false, message: error.message || `Failed to ${action} app ${appId}.` };
  }
} 