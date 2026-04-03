import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';
import { getStripe } from '@/lib/stripe';
import { updateUserSubscriptionDetails } from '@/lib/utils/user-subscription';
export const dynamic = 'force-dynamic';


// Function to fetch Stripe payment details
async function fetchStripePaymentDetails(paymentId: string) {
  const stripe = getStripe();
  try {
    const paymentIntent = await stripe.paymentIntents.retrieve(paymentId);
    
    // Calculate period end as 1 year from payment date (Unix timestamp)
    const paymentDate = new Date(paymentIntent.created * 1000);
    const periodEnd = new Date(paymentDate);
    periodEnd.setFullYear(periodEnd.getFullYear() + 1);
    
    return {
      subscription_id: paymentIntent.id, // Database field name
      customer_id: paymentIntent.customer as string,
      current_period_end: Math.floor(periodEnd.getTime() / 1000), // Unix timestamp (epoch seconds)
      cancel_at_period_end: false, // One-time payments don't auto-cancel
      plan: 'unlimited',
      status: 'active'
    };
  } catch (error) {
    console.error('Error fetching Stripe payment:', error);
    throw new Error('Invalid Stripe payment ID or payment not found');
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const body = await request.json();
    const { is_active, max_seats, organisation_name, website, employees, stripe_payment_id } = body;
    const organizationId = params.id;

    // Exclude employees from updates - employees should not be editable through this endpoint
    if (employees !== undefined) {
      return NextResponse.json(
        { error: 'Employees cannot be updated through this endpoint' },
        { status: 400 }
      );
    }

    // Validate the fields being updated
    if (is_active !== undefined && typeof is_active !== 'boolean') {
      return NextResponse.json(
        { error: 'is_active must be a boolean value' },
        { status: 400 }
      );
    }

    if (max_seats !== undefined && (typeof max_seats !== 'number' || max_seats < 0)) {
      return NextResponse.json(
        { error: 'max_seats must be a non-negative number' },
        { status: 400 }
      );
    }

    if (organisation_name !== undefined && (typeof organisation_name !== 'string' || organisation_name.trim().length === 0)) {
      return NextResponse.json(
        { error: 'organisation_name must be a non-empty string' },
        { status: 400 }
      );
    }

    if (website !== undefined && typeof website !== 'string') {
      return NextResponse.json(
        { error: 'website must be a string' },
        { status: 400 }
      );
    }

    if (stripe_payment_id !== undefined && stripe_payment_id && !stripe_payment_id.startsWith('pi_')) {
      return NextResponse.json(
        { error: 'Invalid Stripe payment ID format. Must start with "pi_"' },
        { status: 400 }
      );
    }

    const orgRef = db.collection('organisations').doc(organizationId);
    const orgDoc = await orgRef.get();

    if (!orgDoc.exists) {
      return NextResponse.json(
        { error: 'Organization not found' },
        { status: 404 }
      );
    }

    // Fetch Stripe payment details if payment ID is provided
    let paymentData = null;
    if (stripe_payment_id !== undefined) {
      if (stripe_payment_id) {
        try {
          paymentData = await fetchStripePaymentDetails(stripe_payment_id);
        } catch (error) {
          return NextResponse.json(
            { error: error instanceof Error ? error.message : 'Failed to fetch Stripe payment details' },
            { status: 400 }
          );
        }
      } else {
        // If empty string, remove payment
        paymentData = null;
      }
    }

    // Build update object with only the fields that are provided
    const updateData: any = {};
    if (is_active !== undefined) {
      updateData.is_active = is_active;
    }
    if (max_seats !== undefined) {
      updateData.max_seats = max_seats;
    }
    if (organisation_name !== undefined) {
      updateData.organisation_name = organisation_name.trim();
    }
    if (website !== undefined) {
      updateData.website = website.trim();
    }
    if (stripe_payment_id !== undefined) {
      updateData.subscription = paymentData; // Database field name
    }

    await orgRef.update(updateData);

    // Update user subscription details for all employees if payment data was updated
    if (stripe_payment_id !== undefined && paymentData !== null) {
      const orgData = await orgRef.get();
      const employees = orgData.data()?.employees || [];
      await updateUserSubscriptionDetails(employees, paymentData);
    }

    const updatedDoc = await orgRef.get();
    const updatedData = updatedDoc.data();

    return NextResponse.json({
      success: true,
      organization: {
        id: updatedDoc.id,
        ...updatedData,
        added_on: updatedData?.added_on?.toDate?.()?.toISOString() || null,
        max_seats: updatedData?.max_seats || null,
        subscription: updatedData?.subscription || null, // Database field name
        employees: updatedData?.employees?.map((emp: any) => ({
          ...emp,
          added_at: emp.added_at?.toDate?.()?.toISOString() || null,
          removed_at: emp.removed_at?.toDate?.()?.toISOString() || null,
        })) || []
      }
    });

  } catch (error) {
    console.error('Error updating organization:', error);
    return NextResponse.json(
      { error: 'Failed to update organization' },
      { status: 500 }
    );
  }
}
