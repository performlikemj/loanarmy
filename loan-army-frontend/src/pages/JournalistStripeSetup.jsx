import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Alert, AlertDescription } from '../components/ui/alert';
import { CheckCircle2, XCircle, Loader2, ExternalLink } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001/api';

const JournalistStripeSetup = () => {
  const auth = useAuth();
  const [accountStatus, setAccountStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchAccountStatus();
  }, []);

  const fetchAccountStatus = async () => {
    try {
      setLoading(true);
      const authHeaders = auth?.token ? { Authorization: `Bearer ${auth.token}` } : {};
      const response = await fetch(`${API_BASE_URL}/stripe/journalist/account-status`, {
        headers: authHeaders
      });

      if (response.ok) {
        const data = await response.json();
        setAccountStatus(data);
      } else {
        throw new Error('Failed to fetch account status');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAccount = async () => {
    try {
      setCreating(true);
      setError(null);

      const response = await fetch(`${API_BASE_URL}/stripe/journalist/onboard`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}),
        },
        body: JSON.stringify({
          refresh_url: window.location.href,
          return_url: window.location.href + '?success=true'
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to create onboarding link');
      }

      const data = await response.json();
      // Redirect to Stripe onboarding
      window.location.href = data.onboarding_url;
    } catch (err) {
      setError(err.message);
      setCreating(false);
    }
  };

  const handleRefreshOnboarding = async () => {
    try {
      setCreating(true);
      setError(null);

      const response = await fetch(`${API_BASE_URL}/stripe/journalist/refresh-onboard`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}),
        },
        body: JSON.stringify({
          refresh_url: window.location.href,
          return_url: window.location.href + '?success=true'
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to refresh onboarding');
      }

      const data = await response.json();
      window.location.href = data.onboarding_url;
    } catch (err) {
      setError(err.message);
      setCreating(false);
    }
  };

  const handleOpenDashboard = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/stripe/journalist/dashboard-link`, {
        method: 'POST',
        headers: auth?.token ? { Authorization: `Bearer ${auth.token}` } : {},
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to get dashboard link');
      }

      const data = await response.json();
      window.open(data.dashboard_url, '_blank');
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto p-6 flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <h1 className="text-3xl font-bold mb-6">Stripe Setup</h1>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Check for success parameter */}
      {new URLSearchParams(window.location.search).get('success') === 'true' && (
        <Alert className="mb-6">
          <AlertDescription>
            Onboarding completed! Your account is being verified. Please refresh the page to see the latest status.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Payment Account Status</CardTitle>
          <CardDescription>
            Connect your Stripe account to receive subscription payments from your subscribers
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {!accountStatus?.has_account ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                You need to create a Stripe Express account to start receiving payments. 
                This process takes about 5 minutes and requires basic business information.
              </p>
              <Button 
                onClick={handleCreateAccount} 
                disabled={creating}
                size="lg"
              >
                {creating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating Account...
                  </>
                ) : (
                  'Create Stripe Account'
                )}
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-4">
                <div className="flex items-center justify-between">
                  <span className="font-medium">Account Created</span>
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="font-medium">Details Submitted</span>
                  {accountStatus.details_submitted ? (
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-500" />
                  )}
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="font-medium">Payments Enabled</span>
                  {accountStatus.charges_enabled ? (
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-500" />
                  )}
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="font-medium">Payouts Enabled</span>
                  {accountStatus.payouts_enabled ? (
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-500" />
                  )}
                </div>
              </div>

              {accountStatus.onboarding_complete ? (
                <div className="space-y-4 pt-4 border-t">
                  <Alert>
                    <CheckCircle2 className="h-4 w-4" />
                    <AlertDescription>
                      Your account is fully set up! You can now set your subscription price and start receiving payments.
                    </AlertDescription>
                  </Alert>
                  
                  <div className="flex gap-4">
                    <Button onClick={handleOpenDashboard} variant="outline">
                      <ExternalLink className="mr-2 h-4 w-4" />
                      Open Stripe Dashboard
                    </Button>
                    <Button onClick={() => window.location.href = '/journalist/pricing'}>
                      Set Subscription Price
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4 pt-4 border-t">
                  <Alert>
                    <AlertDescription>
                      Your onboarding is incomplete. Please continue the setup process in Stripe.
                    </AlertDescription>
                  </Alert>
                  
                  <Button onClick={handleRefreshOnboarding} disabled={creating}>
                    {creating ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Loading...
                      </>
                    ) : (
                      'Continue Onboarding'
                    )}
                  </Button>
                </div>
              )}

              {accountStatus.requirements && accountStatus.requirements.currently_due?.length > 0 && (
                <Alert variant="destructive">
                  <AlertDescription>
                    <strong>Action Required:</strong> Please complete the following requirements:
                    <ul className="list-disc list-inside mt-2">
                      {accountStatus.requirements.currently_due.map(req => (
                        <li key={req}>{req.replace(/_/g, ' ')}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default JournalistStripeSetup;
