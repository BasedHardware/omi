"use client";

import { useState, useMemo } from "react";
import {
  CheckCircle2,
  Filter,
  Download,
  Clock,
  Calendar,
  Star,
  DollarSign,
  MoreVertical,
  MessageCircle,
  Cpu,
  Bell,
  Puzzle,
  User,
  ChevronLeft,
  ChevronRight,
  Plus,
  Check,
  X,
  Eye,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { OmiApp, OmiAppCapability } from "@/lib/services/omi-api/types";
import { useAuth } from "@/components/auth-provider";
import { useAuthFetch } from "@/hooks/useAuthToken";
import { mutate } from "swr";
import { useRouter } from 'next/navigation';
import EditAppDrawer from '@/components/dashboard/edit-app-drawer';

export type SortField = 'installs' | 'rating' | 'created' | null;
export type SortDirection = 'asc' | 'desc';

interface AppsListProps {
  apps: OmiApp[];
  limit?: number;
  minimal?: boolean;
  showActions?: boolean;
  onActionComplete?: (appId: string, action: 'approve' | 'reject') => void;
  onViewDetails?: (appId: string, appName?: string) => void;
  selectedAppIds: Set<string>;
  onSelectedAppIdsChange: (newSelectedAppIds: Set<string>) => void;
  // Sorting props - if not provided, sorting is handled internally (for backward compatibility)
  sortField?: SortField;
  sortDirection?: SortDirection;
  onSortChange?: (field: SortField, direction: SortDirection) => void;
}

export function AppsList({ 
  apps, 
  limit, 
  minimal = false,
  showActions = false,
  onActionComplete,
  onViewDetails,
  selectedAppIds,
  onSelectedAppIdsChange,
  sortField: externalSortField,
  sortDirection: externalSortDirection,
  onSortChange
}: AppsListProps) {
  const [loadingActions, setLoadingActions] = useState<Record<string, boolean>>({});
  const { user } = useAuth();
  const { fetchWithAuth } = useAuthFetch();
  const [editOpen, setEditOpen] = useState(false);
  const [editApp, setEditApp] = useState<OmiApp | null>(null);
  
  // Use external sort state if provided, otherwise use internal state (for backward compatibility)
  const [internalSortField, setInternalSortField] = useState<SortField>(null);
  const [internalSortDirection, setInternalSortDirection] = useState<SortDirection>('desc');
  
  const sortField = externalSortField !== undefined ? externalSortField : internalSortField;
  const sortDirection = externalSortDirection !== undefined ? externalSortDirection : internalSortDirection;
  
  const displayedApps = limit ? apps.slice(0, limit) : apps;

  const handleSort = (field: SortField) => {
    let newDirection: SortDirection;
    
    if (sortField === field) {
      // Toggle direction if clicking the same field
      newDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      // Set new field and default to descending
      newDirection = 'desc';
    }
    
    if (onSortChange) {
      // Use external sort handler
      onSortChange(field, newDirection);
    } else {
      // Use internal sort state (backward compatibility)
      setInternalSortField(field);
      setInternalSortDirection(newDirection);
    }
  };

  const getSortIcon = (field: SortField) => {
    if (sortField !== field) {
      return <ArrowUpDown className="h-3.5 w-3.5 opacity-50" />;
    }
    return sortDirection === 'asc' 
      ? <ArrowUp className="h-3.5 w-3.5" />
      : <ArrowDown className="h-3.5 w-3.5" />;
  };

  const handleReviewAction = async (appId: string, action: 'approve' | 'reject') => {
    if (!user) {
      console.error("Authentication Error: User not logged in.");
      return;
    }

    setLoadingActions(prev => ({ ...prev, [appId]: true }));

    try {
      const response = await fetchWithAuth(`/api/omi/apps/${appId}/review`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || `Failed to ${action} app.`);
      }

      console.log(`App successfully ${action}d.`);
      
      if (onActionComplete) {
        onActionComplete(appId, action);
      }

      mutate(`/api/omi/apps/unapproved`);
      mutate(`/api/omi/apps`);
      
    } catch (error: any) {
      console.error(`Error ${action}ing app ${appId}:`, error);
    } finally {
      setLoadingActions(prev => ({ ...prev, [appId]: false }));
    }
  };

  const handleEdit = (app: OmiApp) => {
    setEditApp(app);
    setEditOpen(true);
  };

  const handleViewDetailsLocal = (appId: string, appName?: string) => {
    if (onViewDetails) {
      onViewDetails(appId, appName);
    } else {
      console.warn('onViewDetails not provided to AppsList');
    }
  };

  const toggleSelectRow = (id: string) => {
    const newSelected = new Set(selectedAppIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    onSelectedAppIdsChange(newSelected);
  };

  const toggleSelectAll = () => {
    if (selectedAppIds.size === displayedApps.length && displayedApps.length > 0) {
      onSelectedAppIdsChange(new Set());
    } else {
      onSelectedAppIdsChange(new Set(displayedApps.map(app => app.id)));
    }
  };


  const getCapabilityIcon = (capability: OmiAppCapability) => {
    switch (capability) {
      case 'memories':
        return <Cpu className="h-4 w-4" />;
      case 'chat':
        return <MessageCircle className="h-4 w-4" />;
      case 'proactive_notification':
        return <Bell className="h-4 w-4" />;
      case 'external_integration':
        return <Puzzle className="h-4 w-4" />;
      case 'persona':
        return <User className="h-4 w-4" />;
      default:
        return null;
    }
  };

  if (!apps || apps.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-4">
        No apps found.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table className="min-w-full">
          <TableHeader>
            <TableRow>
              {!minimal && (
                <TableHead className="w-[40px]">
                  <Checkbox 
                    checked={displayedApps.length > 0 && selectedAppIds.size === displayedApps.length}
                    onCheckedChange={toggleSelectAll}
                    disabled={displayedApps.length === 0}
                  />
                </TableHead>
              )}
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Capabilities</TableHead>
              {!showActions ? (
                <>
                  <TableHead>
                    <button
                      onClick={() => handleSort('installs')}
                      className="flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer -ml-1 px-1 py-1 rounded"
                    >
                      Installs
                      {getSortIcon('installs')}
                    </button>
                  </TableHead>
                  <TableHead>Pricing</TableHead>
                  {!minimal && (
                    <TableHead>
                      <button
                        onClick={() => handleSort('rating')}
                        className="flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer -ml-1 px-1 py-1 rounded"
                      >
                        Rating
                        {getSortIcon('rating')}
                      </button>
                    </TableHead>
                  )}
                </>
              ) : (
                 <TableHead>Pricing</TableHead>
              )}
              {!minimal && (
                <TableHead>
                  <button
                    onClick={() => handleSort('created')}
                    className="flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer -ml-1 px-1 py-1 rounded"
                  >
                    Created
                    {getSortIcon('created')}
                  </button>
                </TableHead>
              )}
              {showActions && (
                  <TableHead className="text-right">Actions</TableHead>
              )}
              {!showActions && (
                 <TableHead className="w-[60px] text-right">
                    Actions
                 </TableHead>
               )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {displayedApps.map((app) => (
              <TableRow key={app.id}>
                {!minimal && (
                  <TableCell>
                    <Checkbox 
                      checked={selectedAppIds.has(app.id)}
                      onCheckedChange={() => toggleSelectRow(app.id)}
                    />
                  </TableCell>
                )}
                <TableCell className="font-medium">
                  <div className="flex items-center gap-3">
                    {app.image ? (
                      <img 
                        src={app.image} 
                        alt={`${app.name} logo`} 
                        className="w-8 h-8 rounded-lg object-cover border"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center flex-shrink-0">
                        <span className="text-xs font-bold">
                          {app.name?.charAt(0)?.toUpperCase() || 'A'} 
                        </span>
                      </div>
                    )}
                    <div>
                      <div className="font-medium">{app.name}</div>
                      <div className="text-xs text-muted-foreground">
                        By {app.author}
                      </div>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge 
                    variant="outline"
                    className="flex items-center gap-1.5 capitalize"
                  >
                    {app.status?.replace("-", " ") || "Unknown"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    {app.capabilities.map((capability: OmiAppCapability) => (
                      <div 
                        key={capability} 
                        className="h-6 w-6 bg-muted rounded-full flex items-center justify-center"
                        title={capability}
                      >
                        {getCapabilityIcon(capability)}
                      </div>
                    ))}
                  </div>
                </TableCell>
                {!showActions ? (
                    <>
                        <TableCell>{app.installs?.toLocaleString() || 0}</TableCell>
                        <TableCell>
                          <Badge variant={app.is_paid ? "default" : "secondary"}>
                            {app.is_paid ? "Paid" : "Free"}
                          </Badge>
                        </TableCell>
                        {!minimal && (
                             <TableCell>
                              {app.rating_avg > 0 ? (
                                <div className="flex items-center gap-1">
                                  <Star className="h-4 w-4 fill-primary text-primary" />
                                  {app.rating_avg.toFixed(1)}
                                </div>
                              ) : (
                                <span className="text-xs text-muted-foreground">No rating</span>
                              )}
                            </TableCell>
                        )}
                    </>
                ) : (
                   <TableCell>
                      <Badge variant={app.is_paid ? "default" : "secondary"}>
                        {app.is_paid ? "Paid" : "Free"}
                      </Badge>
                    </TableCell>
                )}
                {!minimal && (
                  <TableCell>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Calendar className="h-3.5 w-3.5" />
                        {new Date(app.created_at).toLocaleDateString()}
                      </div>
                    </TableCell>
                )}
                <TableCell className="text-right">
                 {showActions ? (
                    <div className="flex gap-1 justify-end">
                      <Button 
                        variant="outline" 
                        size="icon" 
                        className="h-8 w-8"
                        onClick={() => handleViewDetailsLocal(app.id, app.name)}
                        disabled={loadingActions[app.id]}
                        title="View Details"
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button 
                        variant="outline" 
                        size="icon" 
                        className="h-8 w-8 border-green-500 text-green-500 hover:bg-green-50 hover:text-green-600" 
                        onClick={() => handleReviewAction(app.id, 'approve')}
                        disabled={loadingActions[app.id] || app.status === 'approved'}
                        title="Approve"
                      >
                        <Check className="h-4 w-4" />
                      </Button>
                      <Button 
                        variant="outline" 
                        size="icon" 
                        className="h-8 w-8 border-red-500 text-red-500 hover:bg-red-50 hover:text-red-600"
                        onClick={() => handleReviewAction(app.id, 'reject')}
                        disabled={loadingActions[app.id] || app.status === 'rejected'}
                        title="Reject"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ) : (
                     <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreVertical className="h-4 w-4" />
                          <span className="sr-only">Actions</span>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleViewDetailsLocal(app.id, app.name)}>View Details</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleEdit(app)}>Edit</DropdownMenuItem>
                        <DropdownMenuItem 
                          onClick={() => handleReviewAction(app.id, 'reject')}
                          disabled={loadingActions[app.id]}
                          className="text-destructive"
                        >
                          Reject
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive">Delete</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <EditAppDrawer
        open={editOpen}
        onClose={() => setEditOpen(false)}
        app={editApp}
        onSaved={() => {
          mutate(`/api/omi/apps`);
        }}
      />
    </div>
  );
}