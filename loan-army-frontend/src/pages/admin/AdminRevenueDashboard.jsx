import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Alert, AlertDescription } from '../../components/ui/alert';
import { Loader2, DollarSign, TrendingUp, Users, Calendar } from 'lucide-react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001/api';
const ADMIN_API_KEY = import.meta.env.VITE_ADMIN_API_KEY;

const AdminRevenueDashboard = () => {
  const [summary, setSummary] = useState(null);
  const [breakdown, setBreakdown] = useState([]);
  const [trends, setTrends] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchRevenueData();
  }, []);

  const fetchRevenueData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch summary
      const summaryResponse = await fetch(`${API_BASE_URL}/admin/revenue/summary`, {
        headers: {
          'X-API-Key': ADMIN_API_KEY
        }
      });

      if (!summaryResponse.ok) {
        throw new Error('Failed to fetch revenue summary');
      }

      const summaryData = await summaryResponse.json();
      setSummary(summaryData);

      // Fetch breakdown
      const breakdownResponse = await fetch(`${API_BASE_URL}/admin/revenue/breakdown?period=monthly&limit=12`, {
        headers: {
          'X-API-Key': ADMIN_API_KEY
        }
      });

      if (breakdownResponse.ok) {
        const breakdownData = await breakdownResponse.json();
        setBreakdown(breakdownData.breakdown || []);
      }

      // Fetch trends
      const trendsResponse = await fetch(`${API_BASE_URL}/admin/revenue/trends?months=6`, {
        headers: {
          'X-API-Key': ADMIN_API_KEY
        }
      });

      if (trendsResponse.ok) {
        const trendsData = await trendsResponse.json();
        setTrends(trendsData);
      }

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto p-6 flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto p-6">
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  // Prepare chart data
  const chartData = trends?.trends?.labels?.map((label, index) => ({
    month: label,
    revenue: trends.trends.total_revenue[index],
    fees: trends.trends.platform_fees[index],
    subscriptions: trends.trends.subscription_counts[index]
  })) || [];

  return (
    <div className="container mx-auto p-6 max-w-7xl">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Revenue Dashboard</h1>
        <p className="text-muted-foreground">
          Platform maintenance fees and operational costs
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">All-Time Fees</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summary?.all_time?.platform_fees_display || '$0.00'}
            </div>
            <p className="text-xs text-muted-foreground">
              {summary?.all_time?.platform_fee_percent || 10}% of total revenue
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">This Month</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summary?.current_month?.platform_fees_display || '$0.00'}
            </div>
            <p className="text-xs text-muted-foreground">
              {summary?.current_month?.month || 'Current month'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Subscriptions</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summary?.subscriptions?.active_count || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Avg: {summary?.subscriptions?.average_value_display || '$0.00'}/mo
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Growth</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {trends?.growth_percent > 0 ? '+' : ''}{trends?.growth_percent?.toFixed(1) || '0'}%
            </div>
            <p className="text-xs text-muted-foreground">
              Month over month
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Revenue Trend Chart */}
      {chartData.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Platform Fees Over Time</CardTitle>
            <CardDescription>
              Monthly platform maintenance fees collected
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip 
                  formatter={(value) => `$${value.toFixed(2)}`}
                  labelStyle={{ color: '#000' }}
                />
                <Legend />
                <Line 
                  type="monotone" 
                  dataKey="fees" 
                  stroke="#8884d8" 
                  strokeWidth={2}
                  name="Platform Fees"
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Subscription Count Chart */}
      {chartData.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Active Subscriptions</CardTitle>
            <CardDescription>
              Number of active subscriptions over time
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip labelStyle={{ color: '#000' }} />
                <Legend />
                <Bar dataKey="subscriptions" fill="#82ca9d" name="Subscriptions" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Monthly Breakdown Table */}
      {breakdown.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Monthly Breakdown</CardTitle>
            <CardDescription>
              Detailed revenue by month
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-2">Period</th>
                    <th className="text-right p-2">Total Revenue</th>
                    <th className="text-right p-2">Platform Fees</th>
                    <th className="text-right p-2">Subscriptions</th>
                  </tr>
                </thead>
                <tbody>
                  {breakdown.map((item, index) => (
                    <tr key={index} className="border-b">
                      <td className="p-2">{item.period}</td>
                      <td className="text-right p-2">{item.total_revenue_display}</td>
                      <td className="text-right p-2 font-medium">{item.platform_fees_display}</td>
                      <td className="text-right p-2">{item.subscription_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Info Card */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>About Platform Fees</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>
            Platform fees (10% of subscription revenue) are used exclusively for:
          </p>
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li>Server hosting and infrastructure costs</li>
            <li>Payment processing and Stripe fees</li>
            <li>Platform maintenance and updates</li>
            <li>Customer support operations</li>
            <li>Security and compliance measures</li>
          </ul>
          <p className="pt-2">
            This dashboard provides full transparency into how platform fees are collected and allocated.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminRevenueDashboard;

