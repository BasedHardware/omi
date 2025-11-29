'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/src/components/ui/card';
import { Input } from '@/src/components/ui/input';
import { Button } from '@/src/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/src/components/ui/tabs';
import { Shield, Users, DollarSign, BarChart3, Package } from 'lucide-react';
import AppsReview from './components/AppsReview';
import UsersManagement from './components/UsersManagement';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import ConversationCategoriesChart from './components/ConversationCategoriesChart';

export default function AdminDashboard() {
  const [adminKey, setAdminKey] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    // Check if admin key is stored in sessionStorage
    const storedKey = sessionStorage.getItem('admin_key');
    if (storedKey) {
      setAdminKey(storedKey);
      setIsAuthenticated(true);
    }
  }, []);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (adminKey.trim()) {
      sessionStorage.setItem('admin_key', adminKey);
      setIsAuthenticated(true);
    }
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    sessionStorage.removeItem('admin_key');
    setAdminKey('');
  };

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-neutral-50 to-neutral-100 p-4">
        <Card className="w-full max-w-md p-8">
          <div className="mb-6 flex items-center justify-center">
            <div className="rounded-full bg-neutral-900 p-3">
              <Shield className="h-8 w-8 text-white" />
            </div>
          </div>
          <h1 className="mb-2 text-center text-2xl font-bold">Admin Panel</h1>
          <p className="mb-6 text-center text-sm text-neutral-500">
            Enter your admin key to access the dashboard
          </p>
          <form onSubmit={handleLogin}>
            <div className="space-y-4">
              <div>
                <label htmlFor="adminKey" className="text-sm font-medium">
                  Admin Key
                </label>
                <Input
                  id="adminKey"
                  type="password"
                  placeholder="Enter admin key"
                  value={adminKey}
                  onChange={(e) => setAdminKey(e.target.value)}
                  className="mt-1"
                />
              </div>
              <Button type="submit" className="w-full">
                Login
              </Button>
            </div>
          </form>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-50 p-4 md:p-8 pt-24 md:pt-28">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Admin Dashboard</h1>
            <p className="mt-1 text-neutral-500">
              Manage your platform and monitor activity
            </p>
          </div>
          <Button variant="outline" onClick={handleLogout}>
            Logout
          </Button>
        </div>

        {/* Tabs Navigation */}
        <Tabs defaultValue="apps" className="space-y-6">
          <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
            <TabsTrigger value="apps" className="gap-2">
              <Package className="h-4 w-4" />
              <span className="hidden sm:inline">Apps</span>
            </TabsTrigger>
            <TabsTrigger value="users" className="gap-2">
              <Users className="h-4 w-4" />
              <span className="hidden sm:inline">Users</span>
            </TabsTrigger>
            <TabsTrigger value="payments" className="gap-2">
              <DollarSign className="h-4 w-4" />
              <span className="hidden sm:inline">Payments</span>
            </TabsTrigger>
            <TabsTrigger value="analytics" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              <span className="hidden sm:inline">Analytics</span>
            </TabsTrigger>
          </TabsList>

          {/* Apps Review Tab */}
          <TabsContent value="apps" className="space-y-4">
            <AppsReview adminKey={adminKey} />
          </TabsContent>

          {/* Users Management Tab */}
          <TabsContent value="users" className="space-y-4">
            <UsersManagement adminKey={adminKey} />
          </TabsContent>

          {/* Payments Tab */}
          <TabsContent value="payments" className="space-y-4">
            <Card className="p-8">
              <div className="text-center">
                <DollarSign className="mx-auto h-12 w-12 text-neutral-400" />
                <h3 className="mt-4 text-lg font-semibold">Payment Management</h3>
                <p className="mt-2 text-sm text-neutral-500">
                  Coming soon - View subscriptions and revenue
                </p>
              </div>
            </Card>
          </TabsContent>

          {/* Analytics Tab */}
          <TabsContent value="analytics" className="space-y-8">
            <AnalyticsDashboard adminKey={adminKey} />
            <ConversationCategoriesChart adminKey={adminKey} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
