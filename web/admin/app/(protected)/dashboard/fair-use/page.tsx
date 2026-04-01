'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/components/auth-provider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, Search, RefreshCw, ChevronLeft, Shield, ShieldAlert, ShieldOff, ShieldCheck } from 'lucide-react';

interface FlaggedUser {
  uid: string;
  stage: string;
  violation_count_7d?: number;
  violation_count_30d?: number;
  last_classifier_score?: number;
  last_classifier_type?: string;
  updated_at?: string;
  last_violation_at?: string;
  throttle_until?: string;
  restrict_until?: string;
}

interface FairUseEvent {
  id: string;
  case_ref?: string;
  stage?: string;
  classifier_score?: number;
  classifier_type?: string;
  resolved?: boolean;
  resolved_at?: string;
  resolved_by?: string;
  admin_notes?: string;
  created_at?: string;
}

interface UserDetail {
  uid: string;
  state: Record<string, unknown>;
  events: FairUseEvent[];
  profile: {
    email?: string;
    name?: string;
    subscription_plan?: string;
  };
}

function stageBadge(stage: string) {
  switch (stage) {
    case 'warning':
      return <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-300"><ShieldAlert className="h-3 w-3 mr-1" />Warning</Badge>;
    case 'throttle':
      return <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-300"><ShieldOff className="h-3 w-3 mr-1" />Throttle</Badge>;
    case 'restrict':
      return <Badge variant="destructive"><Shield className="h-3 w-3 mr-1" />Restrict</Badge>;
    case 'none':
      return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300"><ShieldCheck className="h-3 w-3 mr-1" />None</Badge>;
    default:
      return <Badge variant="secondary">{stage}</Badge>;
  }
}

function formatDate(dateStr?: string) {
  if (!dateStr) return '-';
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return dateStr;
  }
}

export default function FairUsePage() {
  const { user } = useAuth();
  const [flaggedUsers, setFlaggedUsers] = useState<FlaggedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null);
  const [userLoading, setUserLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchFlaggedUsers = useCallback(async () => {
    if (!user) return;
    try {
      setLoading(true);
      setError(null);
      const idToken = await user.getIdToken();
      const params = new URLSearchParams();
      if (stageFilter) params.set('stage', stageFilter);
      const res = await fetch(`/api/omi/fair-use/flagged?${params}`, {
        headers: { Authorization: `Bearer ${idToken}` },
      });
      if (!res.ok) throw new Error(`Failed to fetch: ${res.status}`);
      const data = await res.json();
      setFlaggedUsers(data.users || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch flagged users');
    } finally {
      setLoading(false);
    }
  }, [user, stageFilter]);

  useEffect(() => {
    fetchFlaggedUsers();
  }, [fetchFlaggedUsers]);

  const fetchUserDetail = async (uid: string) => {
    if (!user) return;
    try {
      setUserLoading(true);
      const idToken = await user.getIdToken();
      const res = await fetch(`/api/omi/fair-use/user/${uid}`, {
        headers: { Authorization: `Bearer ${idToken}` },
      });
      if (!res.ok) throw new Error(`Failed to fetch: ${res.status}`);
      const data = await res.json();
      setSelectedUser(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch user detail');
    } finally {
      setUserLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!user || !searchQuery.trim()) return;
    const query = searchQuery.trim();

    try {
      setUserLoading(true);
      setError(null);
      const idToken = await user.getIdToken();

      if (query.startsWith('FU-')) {
        // Case ref lookup
        const res = await fetch(`/api/omi/fair-use/case/${encodeURIComponent(query)}`, {
          headers: { Authorization: `Bearer ${idToken}` },
        });
        if (!res.ok) {
          if (res.status === 404) {
            setError(`Case ${query} not found`);
            setUserLoading(false);
            return;
          }
          throw new Error(`Failed to fetch: ${res.status}`);
        }
        const caseData = await res.json();
        if (caseData.uid) {
          await fetchUserDetail(caseData.uid);
        }
      } else {
        // UID lookup
        await fetchUserDetail(query);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setUserLoading(false);
    }
  };

  const handleReset = async (uid: string) => {
    if (!user || !confirm('Reset this user\'s fair use state to clean? This will clear all enforcement.')) return;
    try {
      setActionLoading('reset');
      const idToken = await user.getIdToken();
      const res = await fetch(`/api/omi/fair-use/user/${uid}/reset`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${idToken}` },
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      await fetchUserDetail(uid);
      await fetchFlaggedUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSetStage = async (uid: string, stage: string) => {
    if (!user || !confirm(`Set this user's stage to "${stage}"?`)) return;
    try {
      setActionLoading(`stage-${stage}`);
      const idToken = await user.getIdToken();
      const res = await fetch(`/api/omi/fair-use/user/${uid}/set-stage?stage=${stage}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${idToken}` },
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      await fetchUserDetail(uid);
      await fetchFlaggedUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Set stage failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleResolveEvent = async (uid: string, eventId: string) => {
    if (!user || !confirm('Mark this event as resolved?')) return;
    try {
      setActionLoading(`resolve-${eventId}`);
      const idToken = await user.getIdToken();
      const res = await fetch(`/api/omi/fair-use/user/${uid}/resolve-event/${eventId}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${idToken}` },
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      await fetchUserDetail(uid);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Resolve failed');
    } finally {
      setActionLoading(null);
    }
  };

  // User detail view
  if (selectedUser) {
    const state = selectedUser.state;
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => setSelectedUser(null)}>
            <ChevronLeft className="h-4 w-4 mr-1" /> Back
          </Button>
          <h1 className="text-2xl font-bold">User Fair Use Detail</h1>
        </div>

        {error && (
          <div className="bg-destructive/10 text-destructive px-4 py-2 rounded-md text-sm">{error}</div>
        )}

        {/* Profile + State */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Profile</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div><span className="text-muted-foreground">UID:</span> <code className="text-xs">{selectedUser.uid}</code></div>
              <div><span className="text-muted-foreground">Email:</span> {selectedUser.profile.email || '-'}</div>
              <div><span className="text-muted-foreground">Name:</span> {selectedUser.profile.name || '-'}</div>
              <div><span className="text-muted-foreground">Plan:</span> <Badge variant="outline">{selectedUser.profile.subscription_plan || 'basic'}</Badge></div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Enforcement State</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex items-center gap-2"><span className="text-muted-foreground">Stage:</span> {stageBadge(state.stage as string || 'none')}</div>
              <div><span className="text-muted-foreground">Violations (7d):</span> {(state.violation_count_7d as number) ?? 0}</div>
              <div><span className="text-muted-foreground">Violations (30d):</span> {(state.violation_count_30d as number) ?? 0}</div>
              <div><span className="text-muted-foreground">Classifier Score:</span> {(state.last_classifier_score as number)?.toFixed(2) ?? '-'}</div>
              <div><span className="text-muted-foreground">Classifier Type:</span> {(state.last_classifier_type as string) || '-'}</div>
              <div><span className="text-muted-foreground">Last Violation:</span> {formatDate(state.last_violation_at as string)}</div>
              <div><span className="text-muted-foreground">Updated:</span> {formatDate(state.updated_at as string)}</div>
              {typeof state.reset_by === 'string' && (
                <div><span className="text-muted-foreground">Last Reset By:</span> <code className="text-xs">{state.reset_by}</code> at {formatDate(state.reset_at as string)}</div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Actions */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Admin Actions</CardTitle>
            <CardDescription>Changes take effect within 60 seconds (backend cache TTL).</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={actionLoading !== null}
              onClick={() => handleReset(selectedUser.uid)}
            >
              {actionLoading === 'reset' ? 'Resetting...' : 'Reset to Clean'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-yellow-300 text-yellow-700 hover:bg-yellow-50"
              disabled={actionLoading !== null || (state.stage as string) === 'warning'}
              onClick={() => handleSetStage(selectedUser.uid, 'warning')}
            >
              Set Warning
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-orange-300 text-orange-700 hover:bg-orange-50"
              disabled={actionLoading !== null || (state.stage as string) === 'throttle'}
              onClick={() => handleSetStage(selectedUser.uid, 'throttle')}
            >
              Set Throttle
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={actionLoading !== null || (state.stage as string) === 'restrict'}
              onClick={() => handleSetStage(selectedUser.uid, 'restrict')}
            >
              Set Restrict
            </Button>
          </CardContent>
        </Card>

        {/* Events */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Violation Events</CardTitle>
            <CardDescription>{selectedUser.events.length} event(s)</CardDescription>
          </CardHeader>
          <CardContent>
            {selectedUser.events.length === 0 ? (
              <p className="text-muted-foreground text-sm">No events recorded.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case Ref</TableHead>
                    <TableHead>Stage</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {selectedUser.events.map((event) => (
                    <TableRow key={event.id}>
                      <TableCell className="font-mono text-xs">{event.case_ref || '-'}</TableCell>
                      <TableCell>{stageBadge(event.stage || 'none')}</TableCell>
                      <TableCell>{event.classifier_score?.toFixed(2) ?? '-'}</TableCell>
                      <TableCell>{event.classifier_type || '-'}</TableCell>
                      <TableCell className="text-xs">{formatDate(event.created_at)}</TableCell>
                      <TableCell>
                        {event.resolved ? (
                          <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">Resolved</Badge>
                        ) : (
                          <Badge variant="outline" className="bg-red-50 text-red-700 border-red-300">Active</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {!event.resolved && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={actionLoading !== null}
                            onClick={() => handleResolveEvent(selectedUser.uid, event.id)}
                          >
                            {actionLoading === `resolve-${event.id}` ? 'Resolving...' : 'Resolve'}
                          </Button>
                        )}
                        {event.resolved && event.admin_notes && (
                          <span className="text-xs text-muted-foreground">{event.admin_notes}</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  // Main list view
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle className="h-6 w-6 text-orange-500" />
          <h1 className="text-2xl font-bold">Fair Use Admin</h1>
        </div>
        <Button variant="outline" size="sm" onClick={fetchFlaggedUsers} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </Button>
      </div>

      {error && (
        <div className="bg-destructive/10 text-destructive px-4 py-2 rounded-md text-sm">{error}</div>
      )}

      {/* Search */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Lookup</CardTitle>
          <CardDescription>Search by case reference (FU-XXXX) or user UID</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder="FU-A92A2893DF4A or user UID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <Button onClick={handleSearch} disabled={userLoading || !searchQuery.trim()}>
              <Search className="h-4 w-4 mr-1" /> {userLoading ? 'Searching...' : 'Search'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Stage filter */}
      <div className="flex gap-2">
        {['', 'warning', 'throttle', 'restrict'].map((stage) => (
          <Button
            key={stage}
            variant={stageFilter === stage ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStageFilter(stage)}
          >
            {stage === '' ? 'All Stages' : stage.charAt(0).toUpperCase() + stage.slice(1)}
          </Button>
        ))}
      </div>

      {/* Flagged users table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Flagged Users</CardTitle>
          <CardDescription>
            {loading ? 'Loading...' : `${flaggedUsers.length} user(s) with active enforcement`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : flaggedUsers.length === 0 ? (
            <p className="text-muted-foreground text-sm text-center py-8">No flagged users found.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>UID</TableHead>
                  <TableHead>Stage</TableHead>
                  <TableHead>Violations (7d)</TableHead>
                  <TableHead>Violations (30d)</TableHead>
                  <TableHead>Classifier</TableHead>
                  <TableHead>Last Updated</TableHead>
                  <TableHead>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flaggedUsers.map((u) => (
                  <TableRow key={u.uid} className="cursor-pointer hover:bg-accent/50" onClick={() => fetchUserDetail(u.uid)}>
                    <TableCell className="font-mono text-xs">{u.uid.slice(0, 12)}...</TableCell>
                    <TableCell>{stageBadge(u.stage)}</TableCell>
                    <TableCell>{u.violation_count_7d ?? 0}</TableCell>
                    <TableCell>{u.violation_count_30d ?? 0}</TableCell>
                    <TableCell>
                      {u.last_classifier_score !== undefined
                        ? `${u.last_classifier_score.toFixed(2)} (${u.last_classifier_type || '-'})`
                        : '-'}
                    </TableCell>
                    <TableCell className="text-xs">{formatDate(u.updated_at)}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); fetchUserDetail(u.uid); }}>
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
