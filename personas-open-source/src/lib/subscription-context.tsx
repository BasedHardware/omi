'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { auth, db } from './firebase';
import { doc, getDoc, onSnapshot } from 'firebase/firestore';
import { User } from 'firebase/auth';
import { SubscriptionFeatures } from '@/types/subscription';

interface SubscriptionContextType {
  isSubscribed: boolean;
  isLoading: boolean;
  features: SubscriptionFeatures;
  currentPlan: string;
  subscriptionEndsAt: number | null;
}

const defaultFeatures: SubscriptionFeatures = {
  advancedModel: false,
  maxChatsPerDay: 5,
  maxMessagesPerChat: 20,
  prioritySupport: false,
  offlineAccess: false,
};

const proFeatures: SubscriptionFeatures = {
  advancedModel: true,
  maxChatsPerDay: 100,
  maxMessagesPerChat: 100,
  prioritySupport: true,
  offlineAccess: true,
};

const SubscriptionContext = createContext<SubscriptionContextType>({
  isSubscribed: false,
  isLoading: true,
  features: defaultFeatures,
  currentPlan: 'free',
  subscriptionEndsAt: null,
});

export const useSubscription = () => useContext(SubscriptionContext);

export const SubscriptionProvider = ({ children }: { children: ReactNode }) => {
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [features, setFeatures] = useState<SubscriptionFeatures>(defaultFeatures);
  const [currentPlan, setCurrentPlan] = useState('free');
  const [subscriptionEndsAt, setSubscriptionEndsAt] = useState<number | null>(null);

  useEffect(() => {
    const unsubscribe = auth.onAuthStateChanged(async (user: User | null) => {
      if (!user) {
        setIsSubscribed(false);
        setIsLoading(false);
        setFeatures(defaultFeatures);
        setCurrentPlan('free');
        setSubscriptionEndsAt(null);
        return;
      }

      // Get subscription data from Firestore
      const subscriptionRef = doc(db, 'users', user.uid, 'subscriptions', 'active');
      
      try {
        const unsubscribeSnapshot = onSnapshot(subscriptionRef, (snapshot) => {
          if (snapshot.exists()) {
            const data = snapshot.data();
            const isActive = data.status === 'active' || data.status === 'trialing';
            
            setIsSubscribed(isActive);
            setCurrentPlan(isActive ? 'pro' : 'free');
            setFeatures(isActive ? proFeatures : defaultFeatures);
            setSubscriptionEndsAt(data.currentPeriodEnd?.seconds * 1000 || null);
          } else {
            setIsSubscribed(false);
            setFeatures(defaultFeatures);
            setCurrentPlan('free');
            setSubscriptionEndsAt(null);
          }
          setIsLoading(false);
        });
        
        return () => unsubscribeSnapshot();
      } catch (error) {
        console.error('Error fetching subscription:', error);
        setIsSubscribed(false);
        setIsLoading(false);
        setFeatures(defaultFeatures);
        setCurrentPlan('free');
        setSubscriptionEndsAt(null);
      }
    });

    return () => unsubscribe();
  }, []);

  return (
    <SubscriptionContext.Provider
      value={{
        isSubscribed,
        isLoading,
        features,
        currentPlan,
        subscriptionEndsAt,
      }}
    >
      {children}
    </SubscriptionContext.Provider>
  );
}; 