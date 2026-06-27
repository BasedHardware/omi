"use client";

import React, { useState, useMemo, useEffect } from 'react'; 
import { AppsList } from "@/components/dashboard/apps-list";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChevronLeft, ChevronRight, Clock, XCircle, Search } from "lucide-react";
import { useApps as usePublicApprovedApps } from "@/hooks/useApps";
import { useUnapprovedApps } from "@/hooks/useUnapprovedApps";
import { useAuth } from '@/components/auth-provider';
import { useAuthFetch } from '@/hooks/useAuthToken';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { OmiApp } from '@/lib/services/omi-api/types';
import { mutate as swrMutate } from 'swr';
import { AppDetailView } from '@/components/dashboard/app-detail-view';
import { useAppDetails, OmiAppDetailedData } from '@/hooks/useAppDetails';

const Spinner = () => (
  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto my-8"></div>
);

const SpinnerSmall = ({ className }: { className?: string }) => (
  <div className={`animate-spin rounded-full h-4 w-4 border-b-2 border-current ml-2 ${className || ''}`}></div>
);

export default function ReviewsPage() {
  const { apps: publicApps, isLoading: isLoadingPublic, error: errorPublic } = usePublicApprovedApps();
  const { unapprovedApps, isLoadingUnapproved, errorUnapproved } = useUnapprovedApps();
  const { user } = useAuth();
  const { fetchWithAuth } = useAuthFetch();

  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [activeTab, setActiveTab] = useState('pending');
  const [detailAppId, setDetailAppId] = useState<string | null>(null);
  const [detailAppName, setDetailAppName] = useState<string | undefined>(undefined);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedAppIds, setSelectedAppIds] = useState<Set<string>>(new Set());
  const [isBulkProcessing, setIsBulkProcessing] = useState(false);

  // Helper function to parse date from Firestore timestamp or ISO string
  const parseAppDate = (dateField: any): Date | null => {
    if (!dateField) return null;
    if (typeof dateField === 'string') {
      return new Date(dateField);
    }
    if (typeof dateField === 'object' && dateField !== null && typeof dateField._seconds === 'number') {
      return new Date(dateField._seconds * 1000);
    }
    return null; // Or throw an error, or return a default past date
  };

  const { appDetails, isLoadingDetails, errorDetails } = useAppDetails(detailAppId);

  const handleShowAppDetails = (appId: string, appName?: string) => {
    setDetailAppId(appId);
    setDetailAppName(appName);
  };

  const handleCloseAppDetails = () => {
    setDetailAppId(null);
    setDetailAppName(undefined);
  };

  const handleSelectedAppIdsChange = (newSelectedAppIds: Set<string>) => {
    setSelectedAppIds(newSelectedAppIds);
  };

  const handleBulkReviewAction = async (action: 'approve' | 'reject') => {
    if (selectedAppIds.size === 0 || !user) return;

    setIsBulkProcessing(true);
    let successCount = 0;
    let errorCount = 0;

    const reviewPromises = Array.from(selectedAppIds).map(async (appId) => {
      try {
        const response = await fetchWithAuth(`/api/omi/apps/${appId}/review`, {
          method: 'POST',
          body: JSON.stringify({
            action,
            reason: action === 'reject' ? 'Bulk rejection' : undefined
          }),
        });

        if (response.ok) {
          handleAppReviewed(appId, action);
          successCount++;
        } else {
          const errorResult = await response.json().catch(() => ({ message: `Failed to ${action} app ${appId}` }));
          console.error(`Failed to ${action} app ${appId}: ${errorResult.message || response.statusText}`);
          errorCount++;
        }
      } catch (error) {
        console.error(`Error ${action}ing app ${appId} in bulk:`, error);
        errorCount++;
      }
    });

    await Promise.all(reviewPromises);

    setIsBulkProcessing(false);
    setSelectedAppIds(new Set());

    alert(`Bulk ${action} complete. Success: ${successCount}, Failed: ${errorCount}`);
  };

  const handleAppReviewed = async (appId: string, action: 'approve' | 'reject') => {
    if (!user) return;

    try {
      // Invalidate all SWR keys matching the unapproved apps endpoint
      swrMutate(
        (key: any) => Array.isArray(key) && key[0] === '/api/omi/apps/unapproved',
        (currentData: OmiApp[] | undefined) => {
          if (!currentData) return [];
          return currentData.filter(app => app.id !== appId);
        },
        false
      );
    } catch (error) {
      console.error("Error performing optimistic update for review:", error);
    }
  };

  const combinedApps = useMemo(() => {
    if (isLoadingPublic || isLoadingUnapproved || errorPublic || errorUnapproved) {
      return [];
    }
    
    // Only include public apps that are awaiting review or rejected
    // Exclude private apps entirely from the review system
    const reviewableApps = [
      ...(unapprovedApps || []), // These are already public unapproved apps
      ...(publicApps || []).filter(app => 
        app.status === 'pending' || 
        app.status === 'under-review' || 
        app.status === 'rejected'
      )
    ];

    // Filter out apps with 'persona' capability
    const appsWithoutPersona = reviewableApps.filter(app => 
      !app.capabilities?.includes('persona')
    );

    // Default sort by created_at descending (latest first) - apply to filtered list
    appsWithoutPersona.sort((a, b) => {
      const dateA = parseAppDate(a.created_at);
      const dateB = parseAppDate(b.created_at);
      if (dateA && dateB) {
        return dateB.getTime() - dateA.getTime(); // Descending
      }
      if (dateA) return -1; // Put items with valid dates first
      if (dateB) return 1;
      return 0;
    });

    return appsWithoutPersona; // Return the list that excludes persona apps and is sorted
  }, [publicApps, unapprovedApps, isLoadingPublic, isLoadingUnapproved, errorPublic, errorUnapproved]);

  const filteredAppsForTab = useMemo(() => {
    let appsToFilter = combinedApps;

    appsToFilter = appsToFilter.filter(app => {
        switch (activeTab) {
            case 'pending':
                return app.status === 'pending' || app.status === 'under-review';
            case 'rejected':
                return app.status === 'rejected';
            default:
                return false;
        }
    });

    if (searchTerm.trim() !== '') {
      const lowercasedSearchTerm = searchTerm.toLowerCase();
      appsToFilter = appsToFilter.filter(app => 
        (app.name?.toLowerCase().includes(lowercasedSearchTerm)) ||
        (app.author?.toLowerCase().includes(lowercasedSearchTerm))
      );
    }

    return appsToFilter;
  }, [combinedApps, activeTab, searchTerm]);

  const totalFilteredApps = filteredAppsForTab.length;
  const totalPages = Math.ceil(totalFilteredApps / itemsPerPage);

  useEffect(() => {
    if (searchTerm && currentPage !== 1) {
        setCurrentPage(1);
    }
  }, [activeTab, itemsPerPage, filteredAppsForTab.length, currentPage, searchTerm]);

  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const currentApps = filteredAppsForTab.slice(startIndex, endIndex);

  const handlePreviousPage = () => {
    setCurrentPage((prev) => Math.max(prev - 1, 1));
  };
  const handleNextPage = () => {
    setCurrentPage((prev) => Math.min(prev + 1, totalPages || 1));
  };
  const handleItemsPerPageChange = (value: string) => {
    const newItemsPerPage = parseInt(value, 10);
    setItemsPerPage(newItemsPerPage);
    setCurrentPage(1); 
  };

  const isLoading = isLoadingPublic || isLoadingUnapproved;
  const error = errorPublic || errorUnapproved; 

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">App Reviews</h1>
          <p className="text-muted-foreground mt-1">
            Review pending, rejected, and other non-approved applications.
          </p>
        </div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input 
          type="search" 
          placeholder="Search apps by name or author..."
          className="w-full max-w-sm pl-10"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      {/* Bulk Action Buttons */}
      {selectedAppIds.size > 0 && (
        <div className="flex gap-2 mb-4">
          <Button 
            onClick={() => handleBulkReviewAction('approve')} 
            disabled={isBulkProcessing}
            variant="outline"
            className="border-green-500 text-green-500 hover:bg-green-50 hover:text-green-600"
          >
            Approve Selected ({selectedAppIds.size})
            {isBulkProcessing && <SpinnerSmall />}
          </Button>
          <Button 
            onClick={() => handleBulkReviewAction('reject')} 
            disabled={isBulkProcessing}
            variant="outline"
            className="border-red-500 text-red-500 hover:bg-red-50 hover:text-red-600"
          >
            Reject Selected ({selectedAppIds.size})
            {isBulkProcessing && <SpinnerSmall />}
          </Button>
        </div>
      )}

      <Tabs 
        value={activeTab} 
        onValueChange={(value) => setActiveTab(value)} 
        className="space-y-4"
      >
        <TabsList className="bg-muted/50 p-1">
          <TabsTrigger value="pending" className="gap-2">
            <Clock className="h-4 w-4" />
            Pending / Review
          </TabsTrigger>
          <TabsTrigger value="rejected" className="gap-2">
            <XCircle className="h-4 w-4" />
            Rejected
          </TabsTrigger>
        </TabsList>

        {isLoading ? (
          <div className="flex items-center justify-center min-h-[300px]"><Spinner /></div>
        ) : error ? (
          <p className="text-destructive text-center py-4">Error loading apps: {(error as any)?.message || 'An unknown error occurred'}</p>
        ) : (
            <TabsContent value={activeTab} className="mt-0">
                {filteredAppsForTab.length > 0 ? (
                    <>
                        <AppsList 
                            apps={currentApps} 
                            showActions={true} 
                            minimal={false}
                            onActionComplete={handleAppReviewed}
                            onViewDetails={handleShowAppDetails}
                            selectedAppIds={selectedAppIds}
                            onSelectedAppIdsChange={handleSelectedAppIdsChange}
                        /> 
                        {totalPages > 1 && (
                            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4">
                                <div className="flex items-center gap-2">
                                <span className="text-sm text-muted-foreground hidden sm:inline">Rows per page:</span>
                                <Select 
                                    value={itemsPerPage.toString()} 
                                    onValueChange={handleItemsPerPageChange}
                                >
                                    <SelectTrigger className="w-[70px] h-8">
                                    <SelectValue placeholder={itemsPerPage} />
                                    </SelectTrigger>
                                    <SelectContent>
                                    <SelectItem value="10">10</SelectItem>
                                    <SelectItem value="20">20</SelectItem>
                                    <SelectItem value="50">50</SelectItem>
                                    <SelectItem value="100">100</SelectItem>
                                    </SelectContent>
                                </Select>
                                </div>
                                
                                <div className="flex items-center gap-4">
                                <span className="text-sm text-muted-foreground">
                                    Page {currentPage} of {totalPages} ({totalFilteredApps} results)
                                </span>
                                <div className="flex items-center gap-2">
                                    <Button 
                                        variant="outline" 
                                        size="icon" 
                                        className="h-8 w-8" 
                                        onClick={handlePreviousPage} 
                                        disabled={currentPage === 1}
                                    >
                                        <ChevronLeft className="h-4 w-4" />
                                        <span className="sr-only">Previous page</span>
                                    </Button>
                                    <Button 
                                        variant="outline" 
                                        size="icon" 
                                        className="h-8 w-8" 
                                        onClick={handleNextPage} 
                                        disabled={currentPage === totalPages || totalPages === 0} 
                                    >
                                        <ChevronRight className="h-4 w-4" />
                                        <span className="sr-only">Next page</span>
                                    </Button>
                                </div>
                                </div>
                            </div>
                        )}
                    </> 
                ) : ( 
                    <p className="text-center text-muted-foreground py-8">No apps found for this status.</p>
                )}
            </TabsContent>
        )}
      </Tabs>

      <AppDetailView 
        isOpen={!!detailAppId}
        onClose={handleCloseAppDetails}
        appDetails={appDetails}
        appName={detailAppName}
      />

    </div>
  );
}