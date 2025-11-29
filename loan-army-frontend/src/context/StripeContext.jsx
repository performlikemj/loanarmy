import React, { createContext, useContext, useState, useEffect } from 'react';
import { loadStripe } from '@stripe/stripe-js';

const StripeContext = createContext();

export const useStripe = () => {
  const context = useContext(StripeContext);
  if (!context) {
    throw new Error('useStripe must be used within a StripeProvider');
  }
  return context;
};

export const StripeProvider = ({ children }) => {
  const [stripe, setStripe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Get publishable key from backend or environment
  const stripePublishableKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY;

  useEffect(() => {
    const initializeStripe = async () => {
      try {
        if (!stripePublishableKey) {
          console.warn('Stripe publishable key not configured');
          setLoading(false);
          return;
        }

        const stripeInstance = await loadStripe(stripePublishableKey);
        setStripe(stripeInstance);
        setLoading(false);
      } catch (err) {
        console.error('Failed to load Stripe:', err);
        setError(err.message);
        setLoading(false);
      }
    };

    initializeStripe();
  }, [stripePublishableKey]);

  const value = {
    stripe,
    loading,
    error,
    isConfigured: !!stripePublishableKey
  };

  return (
    <StripeContext.Provider value={value}>
      {children}
    </StripeContext.Provider>
  );
};

