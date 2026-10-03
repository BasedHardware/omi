<content>
'use strict';

const app = require('..');
const debug = require('debug')('omi:account');
const { promisify } = require('util');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const { Account } = require('../account.model');
const { MarketplaceAppSubscription } = require('../marketplace-app-subscription.model');
const { User } = require('../user.model');
const { App } = require('../app.model');

// Promisify Stripe methods
const stripeSubscriptionsDel = promisify(stripe.subscriptions.del);
const stripeCustomersDel = promisify(stripe.customers.del);

module.exports = function(Account) {
  // ... existing hooks and methods ...

  // Hook to be executed before an account is deleted
  Account.observe('before delete', async (ctx, next) => {
    const account = ctx.instance || ctx.data;
    if (!account) return next();

    try {
      debug(`Processing account deletion for account ID: ${account.id}`);

      // Fetch user associated with the account
      const user = await User.findById(account.userId);

      if (user && user.stripeCustomerId) {
        debug(`Found Stripe customer ID: ${user.stripeCustomerId} for user ID: ${user.id}`);

        // Find all active marketplace app subscriptions for this user
        const activeSubscriptions = await MarketplaceAppSubscription.find({
          where: {
            userId: user.id,
            status: { inq: ['active', 'past_due', 'trialing'] }
          }
        });

        if (activeSubscriptions && activeSubscriptions.length > 0) {
          debug(`Found ${activeSubscriptions.length} active app subscriptions to cancel.`);
          
          for (const subscription of activeSubscriptions) {
            try {
              // Each subscription's stripeSubscriptionId points to a Stripe subscription ID
              debug(`Cancelling Stripe subscription ID: ${subscription.stripeSubscriptionId} for app ID: ${subscription.appId}`);
              
              // Cancel the subscription in Stripe
              await stripeSubscriptionsDel(subscription.stripeSubscriptionId);
              
              // Optionally, update the local subscription status to reflect cancellation
              // This could be 'canceled' or a similar status
              subscription.status = 'canceled';
              await subscription.save();
              
              debug(`Successfully cancelled subscription ID: ${subscription.stripeSubscriptionId}`);
            } catch (error) {
              // Log the error but continue processing other subscriptions
              console.error(`Failed to cancel Stripe subscription ${subscription.stripeSubscriptionId}:`, error.message);
              // Depending on requirements, you might want to re-throw this error
              // to halt the entire account deletion process if one fails.
            }
          }
        } else {
          debug('No active app subscriptions found for this user.');
        }

        // After all app subscriptions are processed, cancel the main Omi plan subscription
        // This part is likely already handled by the existing logic in #7679,
        // but we ensure it's part of the process.
        if (user.stripeSubscriptionId) {
          debug(`Cancelling main Omi plan subscription ID: ${user.stripeSubscriptionId}`);
          try {
            await stripeSubscriptionsDel(user.stripeSubscriptionId);
            debug(`Successfully cancelled main Omi plan subscription ID: ${user.stripeSubscriptionId}`);
          } catch (error) {
            console.error(`Failed to cancel main Omi plan subscription ${user.stripeSubscriptionId}:`, error.message);
          }
        }

        // Finally, delete the Stripe customer itself
        // This should be done last, after all subscriptions are cancelled.
        debug(`Deleting Stripe customer ID: ${user.stripeCustomerId}`);
        try {
          await stripeCustomersDel(user.stripeCustomerId);
          debug(`Successfully deleted Stripe customer ID: ${user.stripeCustomerId}`);
        } catch (error) {
          // Log error but do not prevent account deletion if customer deletion fails
          // as the subscriptions are the primary concern for billing.
          console.error(`Failed to delete Stripe customer ${user.stripeCustomerId}:`, error.message);
        }
      } else {
        debug(`No associated user or Stripe customer found for account ID: ${account.id}`);
      }

      next();
    } catch (error) {
      console.error(`Error in account deletion hook for account ID: ${account.id}:`, error);
      // Re-throw the error to prevent the account from being deleted if the hook fails.
      // This ensures that we don't leave the user in a state where their account is gone
      // but their subscriptions are still active.
      next(error);
    }
  });
};
</content>