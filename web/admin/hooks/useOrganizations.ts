import { useState, useEffect } from 'react';
import { sendOrganizationInvitation } from '@/lib/services/invitation';
import { useAuthFetch } from '@/hooks/useAuthToken';

export interface Employee {
  email: string;
  is_active: boolean;
  role: 'owner' | 'admin' | 'member';
  uid: string;
  added_at: string | null;
  removed_at: string | null;
}

export interface StripePayment {
  subscription_id: string; // Database field name
  customer_id: string;
  current_period_end: number; // Unix timestamp (epoch seconds)
  cancel_at_period_end: boolean;
  plan: string;
  status: string;
}

export interface UserSubscription {
  subscription_id: string;
  current_period_end: number; // Unix timestamp (epoch seconds)
  cancel_at_period_end: boolean;
  plan: string;
  status: string;
}

export interface Organization {
  id: string;
  organisation_id: string;
  organisation_name: string;
  website: string;
  added_on: string | null;
  is_active?: boolean;
  employees: Employee[];
  max_seats?: number;
  subscription?: StripePayment; // Database field name
}

export interface CreateOrganizationData {
  organisation_name: string;
  website?: string;
  admin_name: string;
  admin_email: string;
  max_seats?: number;
  stripe_payment_id?: string; // UI field name
}

export interface UpdateOrganizationData {
  organisation_name?: string;
  website?: string;
  max_seats?: number;
  is_active?: boolean;
  stripe_payment_id?: string; // UI field name
}

export const useOrganizations = () => {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { fetchWithAuth, token } = useAuthFetch();

  const fetchOrganizations = async () => {
    if (!token) return;
    try {
      setLoading(true);
      setError(null);

      const response = await fetchWithAuth('/api/organizations');
      if (!response.ok) {
        throw new Error('Failed to fetch organizations');
      }

      const data = await response.json();
      setOrganizations(data.organizations);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const createOrganization = async (organizationData: CreateOrganizationData) => {
    try {
      setError(null);

      const response = await fetchWithAuth('/api/organizations', {
        method: 'POST',
        body: JSON.stringify(organizationData),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to create organization');
      }

      // Send invitation to the admin email with the newly created org ID
      try {
        await sendOrganizationInvitation({
          email: organizationData.admin_email,
          role: 'admin',
          isResend: false,
          organisationId: data.organization.id,
        });
        console.log(`Invitation sent to ${organizationData.admin_email} for organization ${data.organization.id}`);
      } catch (inviteError) {
        console.error('Failed to send invitation:', inviteError);
      }

      await fetchOrganizations();
      return data.organization;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  const toggleOrganizationStatus = async (organizationId: string, isActive: boolean) => {
    try {
      setError(null);

      const response = await fetchWithAuth(`/api/organizations/${organizationId}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: isActive }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to update organization');
      }

      setOrganizations((prev) =>
        prev.map((org) => (org.id === organizationId ? { ...org, is_active: isActive } : org)),
      );

      return data.organization;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  const updateMaxSeats = async (organizationId: string, maxSeats: number) => {
    try {
      setError(null);

      const response = await fetchWithAuth(`/api/organizations/${organizationId}`, {
        method: 'PATCH',
        body: JSON.stringify({ max_seats: maxSeats }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to update max seats');
      }

      setOrganizations((prev) =>
        prev.map((org) => (org.id === organizationId ? { ...org, max_seats: maxSeats } : org)),
      );

      return data.organization;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  const updateOrganization = async (organizationId: string, updateData: UpdateOrganizationData) => {
    try {
      setError(null);

      const response = await fetchWithAuth(`/api/organizations/${organizationId}`, {
        method: 'PATCH',
        body: JSON.stringify(updateData),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to update organization');
      }

      setOrganizations((prev) =>
        prev.map((org) => (org.id === organizationId ? { ...org, ...updateData } : org)),
      );

      return data.organization;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  const resendInvitation = async (email: string, role: 'admin' | 'member' = 'member', organisationId?: string) => {
    try {
      setError(null);

      await sendOrganizationInvitation({
        email,
        role,
        isResend: true,
        organisationId,
      });

      console.log(`Invitation resent to ${email}`);
      return { success: true, message: 'Invitation sent successfully' };
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to resend invitation';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  const getCurrentSeatCount = (organization: Organization): number => {
    return organization.employees?.length || 0;
  };

  const canAddEmployee = (organization: Organization): boolean => {
    const currentSeats = getCurrentSeatCount(organization);
    const maxSeats = organization.max_seats;
    return !maxSeats || currentSeats < maxSeats;
  };

  const isEmployeePending = (employee: Employee): boolean => {
    return !employee.uid || employee.uid === '';
  };

  useEffect(() => {
    if (token) {
      fetchOrganizations();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return {
    organizations,
    loading,
    error,
    fetchOrganizations,
    createOrganization,
    toggleOrganizationStatus,
    updateMaxSeats,
    updateOrganization,
    resendInvitation,
    getCurrentSeatCount,
    canAddEmployee,
    isEmployeePending,
  };
};
