import { httpsCallable } from 'firebase/functions';
import { getFirebaseFunctions } from '@/lib/firebase/client';

/**
 * Data structure for inviting a user to an organization
 */
interface InviteUserData {
  /** Email address of the user to invite */
  email: string;
  /** Role to assign to the invited user (defaults to 'member') */
  role?: 'admin' | 'member';
  /** Whether this is a resend of an existing invitation (defaults to false) */
  isResend?: boolean;
  /** Organization ID to invite the user to (required when inviting to a newly created org) */
  organisationId?: string;
}

/**
 * Response from the invitation function
 */
interface InviteUserResponse {
  /** Whether the invitation was sent successfully */
  success: boolean;
  /** Human-readable message about the invitation */
  message: string;
  /** Firestore document ID of the invitation */
  invitationId: string;
}

/**
 * Send an organization invitation to a user via the deployed Firebase callable function.
 * 
 * This function calls the 'inviteUser' Firebase callable function which:
 * - Creates a pending invitation in Firestore (7-day expiry)
 * - Sends an invitation email via Resend
 * - Handles both existing and non-existing users
 * 
 * @param data - Invitation data including email, role, and whether it's a resend
 * @returns Promise resolving to invitation response with success status and invitation ID
 * @throws Error if the invitation fails to send or Firebase function returns an error
 * 
 * @example
 * ```typescript
 * // Send new invitation for newly created org
 * await sendOrganizationInvitation({
 *   email: 'user@example.com',
 *   role: 'admin',
 *   isResend: false,
 *   organisationId: 'org_123456'
 * });
 * 
 * // Resend existing invitation
 * await sendOrganizationInvitation({
 *   email: 'user@example.com',
 *   role: 'member',
 *   isResend: true,
 *   organisationId: 'org_123456'
 * });
 * ```
 */
export const sendOrganizationInvitation = async (data: InviteUserData): Promise<InviteUserResponse> => {
  const inviteUser = httpsCallable<InviteUserData, InviteUserResponse>(getFirebaseFunctions(), 'inviteUser');
  
  try {
    const result = await inviteUser(data);
    return result.data;
  } catch (error: any) {
    console.error('Error sending invitation:', error);
    throw new Error(error.message || 'Failed to send invitation');
  }
};

