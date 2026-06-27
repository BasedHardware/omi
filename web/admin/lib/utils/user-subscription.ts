import admin, { getDb } from '@/lib/firebase/admin';

// Function to update user subscription details for all employees
export async function updateUserSubscriptionDetails(employees: any[], subscriptionData: any) {
  if (!subscriptionData) return;

  const db = getDb();
  const batch = db.batch();
  
  // Create user subscription data (without customer_id)
  const userSubscription = {
    subscription_id: subscriptionData.subscription_id,
    current_period_end: subscriptionData.current_period_end,
    cancel_at_period_end: subscriptionData.cancel_at_period_end,
    plan: subscriptionData.plan,
    status: subscriptionData.status
  };
  
  // Update each employee's user document
  for (const employee of employees) {
    if (employee.uid) {
      const userRef = db.collection('users').doc(employee.uid);
      batch.update(userRef, {
        subscription: userSubscription,
        stripe_customer_id: subscriptionData.customer_id
      });
    }
  }
  
  await batch.commit();
}

// Function to remove subscription details from user documents
export async function removeUserSubscriptionDetails(employees: any[]) {
  const db = getDb();
  const batch = db.batch();
  
  // Remove subscription details from each employee's user document
  for (const employee of employees) {
    if (employee.uid) {
      const userRef = db.collection('users').doc(employee.uid);
      batch.update(userRef, {
        subscription: admin.firestore.FieldValue.delete(),
        stripe_customer_id: admin.firestore.FieldValue.delete()
      });
    }
  }
  
  await batch.commit();
}

// Function to update subscription for a single user
export async function updateSingleUserSubscription(userId: string, subscriptionData: any) {
  if (!subscriptionData) return;

  const db = getDb();
  const userSubscription = {
    subscription_id: subscriptionData.subscription_id,
    current_period_end: subscriptionData.current_period_end,
    cancel_at_period_end: subscriptionData.cancel_at_period_end,
    plan: subscriptionData.plan,
    status: subscriptionData.status
  };
  
  const userRef = db.collection('users').doc(userId);
  await userRef.update({
    subscription: userSubscription,
    stripe_customer_id: subscriptionData.customer_id
  });
}
