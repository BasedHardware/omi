import omiApiClient, { adminInit } from "./client";
import {
  delete_app_v1_apps__app_id__delete,
  get_app_details_v1_apps__app_id__get,
  get_apps_v1_apps_get,
  get_unapproved_public_apps_v1_apps_public_unapproved_get,
  type UnapprovedPublicAppResponse,
} from "./omiApi.generated";
import type { OmiApp, OmiAppInput } from "./types";
import { getDb } from "@/lib/firebase/admin";

const APPS_ENDPOINT = "/v1/apps";

/**
 * Fetches a list of all apps.
 * @param uid - The UID of the authenticated user.
 */
export async function getApps(uid: string): Promise<OmiApp[]> {
  return get_apps_v1_apps_get({}, {}, adminInit(uid));
}

/**
 * Fetches a single app by its ID.
 * @param uid - The UID of the authenticated user.
 */
export async function getAppById(uid: string, appId: string): Promise<OmiApp> {
  return get_app_details_v1_apps__app_id__get(
    { app_id: appId },
    {},
    adminInit(uid),
  );
}

/**
 * Creates a new app.
 * @param uid - The UID of the authenticated user.
 */
export async function createApp(
  uid: string,
  appData: OmiAppInput,
): Promise<OmiApp> {
  // Not wired: POST /v1/apps needs multipart form+file; generated client omits body.
  return await omiApiClient<OmiApp>(APPS_ENDPOINT, uid, {
    method: "POST",
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
  appData: Partial<OmiAppInput>,
): Promise<OmiApp> {
  // Not wired: PATCH /v1/apps/{id} needs multipart form; generated client omits body.
  const endpoint = `${APPS_ENDPOINT}/${appId}`;
  return await omiApiClient<OmiApp>(endpoint, uid, {
    method: "PATCH",
    body: appData,
  });
}

/**
 * Deletes an app by its ID.
 * @param uid - The UID of the authenticated user.
 */
export async function deleteApp(uid: string, appId: string): Promise<void> {
  await delete_app_v1_apps__app_id__delete({ app_id: appId }, {}, adminInit(uid));
}

// Fetch all public unapproved apps
export const getUnapprovedApps = async (
  uid: string,
): Promise<UnapprovedPublicAppResponse[]> => {
  const secretKey = process.env.OMI_API_SECRET_KEY;
  if (!secretKey) {
    throw new Error("OMI_API_SECRET_KEY environment variable is not set.");
  }
  return get_unapproved_public_apps_v1_apps_public_unapproved_get(
    { secret_key: secretKey },
    adminInit(uid),
  );
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
  action: "approve" | "reject",
  reason?: string,
): Promise<{ success: boolean; message?: string }> {
  const db = getDb();
  const appDocRef = db.collection("plugins_data").doc(appId);

  let dataToUpdate: {
    status: string;
    approved: boolean;
  };

  if (action === "approve") {
    dataToUpdate = {
      status: "approved",
      approved: true,
    };
  } else {
    // action === 'reject'
    dataToUpdate = {
      status: "rejected",
      approved: false,
    };
  }

  try {
    await appDocRef.update(dataToUpdate);
    console.log(`App ${appId} status updated to ${action} by user ${uid}.`); // Optional: for server logs
    return { success: true };
  } catch (error: any) {
    console.error(
      `Error updating app ${appId} to ${action} by user ${uid}:`,
      error,
    );
    return {
      success: false,
      message: error.message || `Failed to ${action} app ${appId}.`,
    };
  }
}
