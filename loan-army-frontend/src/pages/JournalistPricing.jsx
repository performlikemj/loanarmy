import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Loader2, DollarSign, Info } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001/api';
const PLATFORM_FEE_PERCENT = 10;

const JournalistPricing = () => {
  const { user } = useAuth();
  const [price, setPrice] = useState('');
  const [currentPrice, setCurrentPrice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchCurrentPrice();
  }, []);

  const fetchCurrentPrice = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/stripe/journalist/my-price`, {
        credentials: 'include'
      });

      if (response.ok) {
        const data = await response.json();
        if (data.has_price) {
          setCurrentPrice(data);
          setPrice((data.plan.price_amount / 100).toFixed(2));
        }
      }
    } catch (err) {
      console.error('Error fetching price:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSavePrice = async (e) => {
    e.preventDefault();
    
    const priceValue = parseFloat(price);
    if (isNaN(priceValue) || priceValue <= 0) {
      setError('Please enter a valid price greater than $0');
      return;
    }

    if (priceValue < 1) {
      setError('Minimum price is $1.00');
      return;
    }

    if (priceValue > 1000) {
      setError('Maximum price is $1,000');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(false);

      const endpoint = currentPrice ? 
        `${API_BASE_URL}/stripe/journalist/update-price` : 
        `${API_BASE_URL}/stripe/journalist/create-price`;
      
      const method = currentPrice ? 'PUT' : 'POST';

      const response = await fetch(endpoint, {
        method,
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ price: priceValue })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to save price');
      }

      const data = await response.json();
      setCurrentPrice(data);
      setSuccess(true);
      
      // Refresh price data
      setTimeout(() => {
        fetchCurrentPrice();
        setSuccess(false);
      }, 2000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const calculateBreakdown = () => {
    const priceValue = parseFloat(price);
    if (isNaN(priceValue) || priceValue <= 0) {
      return null;
    }

    const priceCents = Math.round(priceValue * 100);
    const platformFee = Math.round(priceCents * PLATFORM_FEE_PERCENT / 100);
    const youReceive = priceCents - platformFee;

    return {
      total: priceValue,
      platformFee: platformFee / 100,
      youReceive: youReceive / 100,
      platformFeePercent: PLATFORM_FEE_PERCENT
    };
  };

  const breakdown = calculateBreakdown();

  if (loading) {
    return (
      <div className="container mx-auto p-6 flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <h1 className="text-3xl font-bold mb-6">Subscription Pricing</h1>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert className="mb-6">
          <AlertDescription>
            Subscription price {currentPrice ? 'updated' : 'created'} successfully!
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Set Your Monthly Price</CardTitle>
            <CardDescription>
              Choose how much subscribers will pay per month to access your content
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSavePrice} className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="price">Monthly Subscription Price (USD)</Label>
                <div className="relative">
                  <DollarSign className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="price"
                    type="number"
                    step="0.01"
                    min="1"
                    max="1000"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    placeholder="9.99"
                    className="pl-9"
                    required
                  />
                </div>
                <p className="text-sm text-muted-foreground">
                  Minimum: $1.00 • Maximum: $1,000.00
                </p>
              </div>

              <Button type="submit" disabled={saving} className="w-full">
                {saving ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  currentPrice ? 'Update Price' : 'Set Price'
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-6">
          {currentPrice && (
            <Card>
              <CardHeader>
                <CardTitle>Current Price</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">
                  {currentPrice.plan.price_display}/month
                </div>
                <p className="text-sm text-muted-foreground mt-2">
                  You receive: {currentPrice.breakdown.journalist_receives_display}/month
                </p>
              </CardContent>
            </Card>
          )}

          {breakdown && (
            <Card>
              <CardHeader>
                <CardTitle>Revenue Breakdown</CardTitle>
                <CardDescription>
                  How your subscription revenue is split
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Subscription Price</span>
                    <span className="font-medium">${breakdown.total.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-sm text-muted-foreground">
                    <span>Platform Fee ({breakdown.platformFeePercent}%)</span>
                    <span>-${breakdown.platformFee.toFixed(2)}</span>
                  </div>
                  <div className="border-t pt-2 flex justify-between font-bold">
                    <span>You Receive</span>
                    <span className="text-green-600">${breakdown.youReceive.toFixed(2)}</span>
                  </div>
                </div>

                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertDescription className="text-xs">
                    The {PLATFORM_FEE_PERCENT}% platform fee covers maintenance, hosting, 
                    and operational costs. All fees are transparently tracked and used 
                    to improve the platform.
                  </AlertDescription>
                </Alert>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Pricing Tips</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>• Start with a price that reflects your content value</p>
              <p>• Most journalists charge between $5-$15/month</p>
              <p>• You can update your price anytime</p>
              <p>• Existing subscribers keep their current price</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default JournalistPricing;

