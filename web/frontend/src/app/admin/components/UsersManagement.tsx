'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/src/components/ui/card';
import { Input } from '@/src/components/ui/input';
import { Button } from '@/src/components/ui/button';
import { Badge } from '@/src/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/src/components/ui/table';
import { useToast } from '@/src/hooks/use-toast';
import { Toaster } from '@/src/components/ui/toaster';
import {
  Users,
  Search,
  Loader2,
  Mail,
  Calendar,
  Activity,
} from 'lucide-react';

interface UsersManagementProps {
  adminKey: string;
}

interface User {
  uid: string;
  email?: string;
  created_at?: any;
  last_active?: any;
  memory_count?: number;
  conversation_count?: number;
}

export default function UsersManagement({ adminKey }: UsersManagementProps) {
  const { toast } = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const loadUsers = async () => {
    setLoading(true);
    try {
      // TODO: Create backend endpoint /v1/admin/users
      toast({
        title: 'Coming Soon',
        description: 'User management backend endpoint needs to be created',
        variant: 'destructive',
      });
      // const response = await fetch('/api/admin/users', {
      //   headers: { 'x-admin-key': adminKey },
      // });
      // const data = await response.json();
      // setUsers(data);
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to load users',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const filteredUsers = users.filter((user) =>
    user.email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    user.uid.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <>
      <div>
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold">User Management</h2>
            <p className="mt-1 text-sm text-neutral-500">
              View and manage all platform users
            </p>
          </div>
          <Button onClick={loadUsers} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading...
              </>
            ) : (
              <>
                <Activity className="mr-2 h-4 w-4" />
                Load Users
              </>
            )}
          </Button>
        </div>

        {/* Stats Cards */}
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-neutral-500">Total Users</p>
                <p className="mt-1 text-3xl font-bold">{users.length}</p>
              </div>
              <div className="rounded-full bg-blue-100 p-3">
                <Users className="h-6 w-6 text-blue-600" />
              </div>
            </div>
          </Card>
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-neutral-500">Search Results</p>
                <p className="mt-1 text-3xl font-bold">{filteredUsers.length}</p>
              </div>
              <div className="rounded-full bg-green-100 p-3">
                <Search className="h-6 w-6 text-green-600" />
              </div>
            </div>
          </Card>
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-neutral-500">Active Today</p>
                <p className="mt-1 text-3xl font-bold">-</p>
              </div>
              <div className="rounded-full bg-purple-100 p-3">
                <Activity className="h-6 w-6 text-purple-600" />
              </div>
            </div>
          </Card>
        </div>

        {/* Search */}
        <Card className="mb-6 p-4">
          <div className="flex items-center gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
              <Input
                placeholder="Search by email or UID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>
        </Card>

        {/* Users Table */}
        <Card className="overflow-x-auto">
          {users.length === 0 ? (
            <div className="p-12 text-center">
              <Users className="mx-auto h-16 w-16 text-neutral-300" />
              <h3 className="mt-4 text-lg font-semibold">No Users Loaded</h3>
              <p className="mt-2 text-sm text-neutral-500">
                Click "Load Users" button to fetch users from the database.
              </p>
              <div className="mt-6 rounded-lg bg-amber-50 p-4 text-left">
                <p className="text-sm font-semibold text-amber-900">
                  ⚠️ Backend Endpoint Required
                </p>
                <p className="mt-2 text-sm text-amber-700">
                  To enable user management, add this endpoint to the backend:
                </p>
                <code className="mt-2 block rounded bg-amber-100 p-2 text-xs text-amber-900">
                  GET /v1/admin/users (requires ADMIN_KEY header)
                </code>
              </div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[300px]">User</TableHead>
                  <TableHead className="w-[150px]">Joined</TableHead>
                  <TableHead className="w-[120px]">Memories</TableHead>
                  <TableHead className="w-[120px]">Conversations</TableHead>
                  <TableHead className="w-[150px]">Last Active</TableHead>
                  <TableHead className="w-[150px] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.map((user) => (
                  <TableRow key={user.uid}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-neutral-200">
                          <Users className="h-5 w-5 text-neutral-600" />
                        </div>
                        <div>
                          <div className="font-medium">{user.email || 'No email'}</div>
                          <div className="text-xs text-neutral-500 font-mono">{user.uid}</div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        {user.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{user.memory_count || 0}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{user.conversation_count || 0}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm text-neutral-500">
                        {user.last_active ? new Date(user.last_active).toLocaleDateString() : 'Never'}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="outline">
                        View Details
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        <Toaster />
      </div>
    </>
  );
}
