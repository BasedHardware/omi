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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/src/components/ui/dialog';
import { Label } from '@/src/components/ui/label';
import { useToast } from '@/src/hooks/use-toast';
import { Toaster } from '@/src/components/ui/toaster';
import {
  getUnapprovedApps,
  approveApp,
  rejectApp,
  setAppPopular,
  UnapprovedApp,
} from '@/src/lib/api/admin';
import {
  CheckCircle,
  XCircle,
  Eye,
  Star,
  Clock,
  Loader2,
  TrendingUp,
} from 'lucide-react';

interface AppsReviewProps {
  adminKey: string;
}

export default function AppsReview({ adminKey }: AppsReviewProps) {
  const { toast } = useToast();
  const [apps, setApps] = useState<UnapprovedApp[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedApp, setSelectedApp] = useState<UnapprovedApp | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (adminKey) {
      loadApps();
    }
  }, [adminKey]);

  const loadApps = async () => {
    setLoading(true);
    try {
      const unapprovedApps = await getUnapprovedApps(adminKey);
      setApps(unapprovedApps);
      toast({
        title: 'Success',
        description: `Loaded ${unapprovedApps.length} apps pending review`,
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to load apps',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (app: UnapprovedApp) => {
    setActionLoading(app.id);
    try {
      await approveApp(app.id, app.uid, adminKey);
      setApps(apps.filter((a) => a.id !== app.id));
      toast({
        title: 'App Approved',
        description: `${app.name} has been approved and the developer has been notified.`,
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to approve app',
        variant: 'destructive',
      });
    } finally {
      setActionLoading(null);
      setDetailDialogOpen(false);
    }
  };

  const handleReject = async (app: UnapprovedApp) => {
    setActionLoading(app.id);
    try {
      await rejectApp(app.id, app.uid, adminKey);
      setApps(apps.filter((a) => a.id !== app.id));
      toast({
        title: 'App Rejected',
        description: `${app.name} has been rejected and the developer has been notified.`,
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to reject app',
        variant: 'destructive',
      });
    } finally {
      setActionLoading(null);
      setDetailDialogOpen(false);
    }
  };

  const handleSetPopular = async (app: UnapprovedApp, value: boolean) => {
    setActionLoading(app.id);
    try {
      await setAppPopular(app.id, value, adminKey);
      toast({
        title: 'Success',
        description: `${app.name} ${value ? 'marked as' : 'removed from'} popular apps.`,
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to update app',
        variant: 'destructive',
      });
    } finally {
      setActionLoading(null);
    }
  };

  const openDetailDialog = (app: UnapprovedApp) => {
    setSelectedApp(app);
    setDetailDialogOpen(true);
  };

  const filteredApps = apps.filter((app) =>
    app.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    app.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    app.author?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatDate = (timestamp: any) => {
    if (!timestamp) return 'N/A';
    const date = timestamp.seconds
      ? new Date(timestamp.seconds * 1000)
      : new Date(timestamp);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <>
      <div>
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold">App Review</h2>
            <p className="mt-1 text-sm text-neutral-500">
              Review and manage app submissions
            </p>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-neutral-500">Pending Review</p>
                <p className="mt-1 text-3xl font-bold">{apps.length}</p>
              </div>
              <div className="rounded-full bg-amber-100 p-3">
                <Clock className="h-6 w-6 text-amber-600" />
              </div>
            </div>
          </Card>
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-neutral-500">Needs Attention</p>
                <p className="mt-1 text-3xl font-bold">
                  {apps.filter((a) => a.status === 'under-review').length}
                </p>
              </div>
              <div className="rounded-full bg-blue-100 p-3">
                <Eye className="h-6 w-6 text-blue-600" />
              </div>
            </div>
          </Card>
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-neutral-500">Search Results</p>
                <p className="mt-1 text-3xl font-bold">{filteredApps.length}</p>
              </div>
              <div className="rounded-full bg-green-100 p-3">
                <TrendingUp className="h-6 w-6 text-green-600" />
              </div>
            </div>
          </Card>
        </div>

        {/* Search and Filters */}
        <Card className="mb-6 p-4">
          <div className="flex items-center gap-4">
            <Input
              placeholder="Search apps by name, description, or author..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1"
            />
            <Button onClick={() => loadApps(adminKey)} disabled={loading}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                'Refresh'
              )}
            </Button>
          </div>
        </Card>

        {/* Apps Table */}
        <Card className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[300px] min-w-[250px]">App</TableHead>
                <TableHead className="w-[120px]">Author</TableHead>
                <TableHead className="w-[140px]">Category</TableHead>
                <TableHead className="w-[180px]">Capabilities</TableHead>
                <TableHead className="w-[140px]">Submitted</TableHead>
                <TableHead className="w-[120px]">Status</TableHead>
                <TableHead className="w-[200px] text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredApps.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-neutral-500">
                    {loading ? 'Loading apps...' : 'No apps pending review'}
                  </TableCell>
                </TableRow>
              ) : (
                filteredApps.map((app) => (
                  <TableRow key={app.id}>
                    <TableCell className="w-[300px] min-w-[250px]">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-neutral-200 flex items-center justify-center flex-shrink-0 overflow-hidden">
                          {app.image ? (
                            <img
                              src={app.image}
                              alt={app.name}
                              className="h-full w-full object-cover"
                              onError={(e) => {
                                const target = e.currentTarget;
                                target.style.display = 'none';
                                const parent = target.parentElement;
                                if (parent) {
                                  parent.innerHTML = `<span class="text-neutral-500 font-semibold text-lg">${app.name.charAt(0).toUpperCase()}</span>`;
                                }
                              }}
                            />
                          ) : (
                            <span className="text-neutral-500 font-semibold text-lg">
                              {app.name.charAt(0).toUpperCase()}
                            </span>
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="font-medium truncate">{app.name}</div>
                          <div className="text-sm text-neutral-500 line-clamp-1">
                            {app.description}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="w-[120px]">
                      <div className="text-sm truncate">{app.author || 'Unknown'}</div>
                    </TableCell>
                    <TableCell className="w-[140px]">
                      <Badge variant="outline" className="whitespace-nowrap">{app.category || 'Other'}</Badge>
                    </TableCell>
                    <TableCell className="w-[180px]">
                      <div className="flex flex-wrap gap-1">
                        {app.capabilities?.slice(0, 1).map((cap) => (
                          <Badge key={cap} variant="secondary" className="text-xs whitespace-nowrap">
                            {cap}
                          </Badge>
                        ))}
                        {(app.capabilities?.length || 0) > 1 && (
                          <Badge variant="secondary" className="text-xs">
                            +{(app.capabilities?.length || 0) - 1}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="w-[140px]">
                      <div className="text-sm whitespace-nowrap">{formatDate(app.created_at)}</div>
                    </TableCell>
                    <TableCell className="w-[120px]">
                      <Badge
                        variant={
                          app.status === 'approved'
                            ? 'default'
                            : app.status === 'rejected'
                              ? 'destructive'
                              : 'secondary'
                        }
                        className="whitespace-nowrap"
                      >
                        {app.status || 'under-review'}
                      </Badge>
                    </TableCell>
                    <TableCell className="w-[200px] text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openDetailDialog(app)}
                          disabled={actionLoading === app.id}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="default"
                          onClick={() => handleApprove(app)}
                          disabled={actionLoading === app.id}
                        >
                          {actionLoading === app.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <CheckCircle className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleReject(app)}
                          disabled={actionLoading === app.id}
                        >
                          <XCircle className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Card>

        {/* App Detail Dialog */}
        <Dialog open={detailDialogOpen} onOpenChange={setDetailDialogOpen}>
          <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
            {selectedApp && (
              <>
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-3">
                    <div className="h-12 w-12 rounded-lg bg-neutral-200 flex items-center justify-center flex-shrink-0 overflow-hidden">
                      {selectedApp.image ? (
                        <img
                          src={selectedApp.image}
                          alt={selectedApp.name}
                          className="h-full w-full object-cover"
                          onError={(e) => {
                            const target = e.currentTarget;
                            target.style.display = 'none';
                            const parent = target.parentElement;
                            if (parent) {
                              parent.innerHTML = `<span class="text-neutral-500 font-semibold text-xl">${selectedApp.name.charAt(0).toUpperCase()}</span>`;
                            }
                          }}
                        />
                      ) : (
                        <span className="text-neutral-500 font-semibold text-xl">
                          {selectedApp.name.charAt(0).toUpperCase()}
                        </span>
                      )}
                    </div>
                    {selectedApp.name}
                  </DialogTitle>
                  <DialogDescription>
                    Review app details and decide on approval
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                  <div>
                    <Label className="font-semibold">Description</Label>
                    <p className="mt-1 text-sm text-neutral-600">
                      {selectedApp.description || 'No description provided'}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label className="font-semibold">Author</Label>
                      <p className="mt-1 text-sm">{selectedApp.author || 'Unknown'}</p>
                    </div>
                    <div>
                      <Label className="font-semibold">Category</Label>
                      <p className="mt-1 text-sm">{selectedApp.category || 'Other'}</p>
                    </div>
                    <div>
                      <Label className="font-semibold">Installs</Label>
                      <p className="mt-1 text-sm">{selectedApp.installs || 0}</p>
                    </div>
                    <div>
                      <Label className="font-semibold">Rating</Label>
                      <p className="mt-1 text-sm">
                        {selectedApp.rating_avg?.toFixed(1) || 'N/A'} (
                        {selectedApp.rating_count || 0} reviews)
                      </p>
                    </div>
                  </div>

                  <div>
                    <Label className="font-semibold">Capabilities</Label>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selectedApp.capabilities?.map((cap) => (
                        <Badge key={cap}>{cap}</Badge>
                      )) || 'None'}
                    </div>
                  </div>

                  {selectedApp.external_integration && (
                    <div>
                      <Label className="font-semibold">External Integration</Label>
                      <div className="mt-2 rounded-lg bg-neutral-50 p-3">
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          <div>
                            <span className="text-neutral-500">Webhook URL:</span>
                            <p className="break-all">
                              {selectedApp.external_integration.webhook_url}
                            </p>
                          </div>
                          <div>
                            <span className="text-neutral-500">Setup URL:</span>
                            <p className="break-all">
                              {selectedApp.external_integration.setup_completed_url ||
                                'N/A'}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div>
                    <Label className="font-semibold">Metadata</Label>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-neutral-500">App ID:</span>
                        <p className="font-mono text-xs">{selectedApp.id}</p>
                      </div>
                      <div>
                        <span className="text-neutral-500">Owner UID:</span>
                        <p className="font-mono text-xs">{selectedApp.uid}</p>
                      </div>
                      <div>
                        <span className="text-neutral-500">Created:</span>
                        <p>{formatDate(selectedApp.created_at)}</p>
                      </div>
                      <div>
                        <span className="text-neutral-500">Updated:</span>
                        <p>{formatDate(selectedApp.updated_at)}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <DialogFooter className="gap-2">
                  <Button
                    variant="outline"
                    onClick={() =>
                      handleSetPopular(selectedApp, !selectedApp.popular)
                    }
                    disabled={actionLoading === selectedApp.id}
                  >
                    <Star
                      className={`mr-2 h-4 w-4 ${selectedApp.popular ? 'fill-current' : ''}`}
                    />
                    {selectedApp.popular ? 'Remove from Popular' : 'Mark as Popular'}
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => handleReject(selectedApp)}
                    disabled={actionLoading === selectedApp.id}
                  >
                    {actionLoading === selectedApp.id ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <XCircle className="mr-2 h-4 w-4" />
                    )}
                    Reject
                  </Button>
                  <Button
                    onClick={() => handleApprove(selectedApp)}
                    disabled={actionLoading === selectedApp.id}
                  >
                    {actionLoading === selectedApp.id ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <CheckCircle className="mr-2 h-4 w-4" />
                    )}
                    Approve
                  </Button>
                </DialogFooter>
              </>
            )}
          </DialogContent>
        </Dialog>

        <Toaster />
      </div>
    </>
  );
}
