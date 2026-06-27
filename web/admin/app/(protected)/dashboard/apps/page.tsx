'use client';

import React, { useState, useMemo, useEffect } from 'react';
import { useDebouncedCallback } from 'use-debounce';
import { AppsList } from "@/components/dashboard/apps-list";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Plus, ChevronLeft, ChevronRight, Filter as FilterIcon, Cpu, MessageCircle, Bell, Puzzle, User } from "lucide-react";
import { useApps as usePublicApprovedApps } from "@/hooks/useApps";
import { useUnapprovedApps } from "@/hooks/useUnapprovedApps";
import { usePrivateApps } from "@/hooks/usePrivateApps";
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from "@/components/ui/select";
import { OmiApp, OmiAppCapability } from '@/lib/services/omi-api/types';
import { AppDetailView } from '@/components/dashboard/app-detail-view';
import { useAppDetails } from '@/hooks/useAppDetails';
import { WelcomeOverview } from '@/components/dashboard/welcome-overview';

// Simple spinner placeholder (consider moving to shared UI)
const Spinner = () => (
  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto my-8"></div>
);

// Helper for date filtering (you might want to use a library like date-fns for more complex logic)
const filterByDate = (dateStr: string, range: string): boolean => {
  if (range === 'all') return true;
  const date = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  switch (range) {
    case 'today':
      return date >= today;
    case 'week':
      const startOfWeek = new Date(today);
      startOfWeek.setDate(today.getDate() - today.getDay()); // Assuming Sunday start
      return date >= startOfWeek;
    case 'month':
      const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
      return date >= startOfMonth;
    case 'year':
      const startOfYear = new Date(now.getFullYear(), 0, 1);
      return date >= startOfYear;
    default:
      return true;
  }
};

// Define possible capabilities (excluding persona)
const ALL_CAPABILITIES: OmiAppCapability[] = [
  'memories',
  'chat',
  'proactive_notification',
  'external_integration'
];

// Helper to get icon for capability (similar to AppsList)
const getCapabilityIcon = (capability: OmiAppCapability, className = "h-4 w-4") => {
  switch (capability) {
    case 'memories':
      return <Cpu className={className} />;
    case 'chat':
      return <MessageCircle className={className} />;
    case 'proactive_notification':
      return <Bell className={className} />;
    case 'external_integration':
      return <Puzzle className={className} />;
    case 'persona':
      return <User className={className} />;
    default:
      return null;
  }
};

export default function AppsPage() {
  // --- Fetch Data from Multiple Sources ---
  const { apps: publicApps, isLoading: isLoadingPublic, error: errorPublic } = usePublicApprovedApps();
  const { unapprovedApps, isLoadingUnapproved, errorUnapproved } = useUnapprovedApps();
  const { privateApps, isLoadingPrivate, errorPrivate } = usePrivateApps();
  // --- End Fetch Data ---

  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(100);

  // --- Filter State ---
  const [statusFilter, setStatusFilter] = useState('approved');
  const [privacyFilter, setPrivacyFilter] = useState('public');
  const [priceFilter, setPriceFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCapabilities, setSelectedCapabilities] = useState<Set<OmiAppCapability>>(new Set());
  const [selectedAppIds, setSelectedAppIds] = useState<Set<string>>(new Set());
  
  // --- Sort State ---
  const [sortField, setSortField] = useState<'installs' | 'rating' | 'created' | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  
  // --- Sidebar State ---
  const [detailAppId, setDetailAppId] = useState<string | null>(null);
  const [detailAppName, setDetailAppName] = useState<string | undefined>(undefined);
  // --- End Filter State ---

  // --- Combine and Filter Logic ---
  // Combine data only when all sources are loaded and error-free
  const combinedApps = useMemo(() => {
    if (isLoadingPublic || isLoadingUnapproved || isLoadingPrivate || errorPublic || errorUnapproved || errorPrivate) {
      // If any source is loading or has an error, don't combine yet
      return [];
    }
    // Combine arrays, ensuring they exist
    const allFetchedApps = [
      ...(publicApps || []),
      ...(unapprovedApps || []),
      ...(privateApps || [])
    ];
    // Optional: Add de-duplication logic here if needed, e.g., based on app.id
    // const uniqueApps = Array.from(new Map(allFetchedApps.map(app => [app.id, app])).values());
    // return uniqueApps; 
    return allFetchedApps;
  }, [publicApps, unapprovedApps, privateApps, isLoadingPublic, isLoadingUnapproved, isLoadingPrivate, errorPublic, errorUnapproved, errorPrivate]);

  // Filter the combined data
  const filteredApps = useMemo(() => {
    // Use combinedApps as the source for filtering
    return combinedApps.filter(app => {
      // Exclude persona apps by default
      if (app.capabilities?.includes('persona')) return false;
      
      // Status Filter
      if (statusFilter !== 'all' && app.status !== statusFilter) return false;
      
      // Privacy Filter (Handle boolean app.private correctly)
      if (privacyFilter === 'public' && app.private === true) return false;
      if (privacyFilter === 'private' && app.private === false) return false;

      // Price Filter
      if (priceFilter === 'free' && app.is_paid === true) return false;
      if (priceFilter === 'paid' && app.is_paid === false) return false;

      // Date Filter
      if (!filterByDate(app.created_at, dateFilter)) return false;

      // Search Term Filter (checking name and author)
      if (searchTerm) {
        const lowerSearchTerm = searchTerm.toLowerCase();
        const nameMatch = app.name?.toLowerCase().includes(lowerSearchTerm) || false;
        const authorMatch = app.author?.toLowerCase().includes(lowerSearchTerm) || false;
        if (!nameMatch && !authorMatch) return false;
      }

      // Capabilities Filter
      if (selectedCapabilities.size > 0) {
          // Check if app.capabilities contains ALL selectedCapabilities
          const hasAllCapabilities = Array.from(selectedCapabilities).every(cap => 
              app.capabilities?.includes(cap)
          );
          if (!hasAllCapabilities) return false;
      }

      return true; // Include app if all checks pass
    });
    // Ensure dependencies include combinedApps and all filter states
  }, [combinedApps, statusFilter, privacyFilter, priceFilter, dateFilter, searchTerm, selectedCapabilities]);
  
  // Sort the filtered apps before pagination
  const sortedAndFilteredApps = useMemo(() => {
    if (!sortField) return filteredApps;
    
    const sorted = [...filteredApps].sort((a, b) => {
      let aValue: number;
      let bValue: number;
      
      switch (sortField) {
        case 'installs':
          aValue = a.installs || 0;
          bValue = b.installs || 0;
          break;
        case 'rating':
          aValue = a.rating_avg || 0;
          bValue = b.rating_avg || 0;
          break;
        case 'created':
          aValue = new Date(a.created_at).getTime();
          bValue = new Date(b.created_at).getTime();
          break;
        default:
          return 0;
      }
      
      return sortDirection === 'asc' ? aValue - bValue : bValue - aValue;
    });
    
    return sorted;
  }, [filteredApps, sortField, sortDirection]); 
  // --- End Combine and Filter Logic ---

  // --- Pagination Calculation (based on sortedAndFilteredApps) ---
  const totalFilteredApps = sortedAndFilteredApps.length;
  const totalPages = Math.ceil(totalFilteredApps / itemsPerPage);

  // Adjust current page effect (use sortedAndFilteredApps.length check in dependency)
  useEffect(() => {
    const effectiveTotalPages = Math.ceil(sortedAndFilteredApps.length / itemsPerPage); // Use sorted length directly
    if (currentPage > effectiveTotalPages && effectiveTotalPages > 0) {
      setCurrentPage(effectiveTotalPages);
    } else if (currentPage !== 1 && effectiveTotalPages === 0 && combinedApps.length > 0) {
        // Reset if filters yield 0 from a non-empty combined list
        setCurrentPage(1);
    } else if (currentPage > 1 && effectiveTotalPages === 1) {
        setCurrentPage(1);
    }
  }, [currentPage, itemsPerPage, sortedAndFilteredApps.length, combinedApps.length]); // Depend on sorted length

  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const currentApps = sortedAndFilteredApps.slice(startIndex, endIndex);
  // --- End Pagination Calculation ---

  // --- Handlers ---
  const handlePreviousPage = () => {
    setCurrentPage((prev) => Math.max(prev - 1, 1));
  };

  const handleNextPage = () => {
    setCurrentPage((prev) => Math.min(prev + 1, totalPages || 1));
  };

  const handleSelectedAppIdsChange = (newSelectedAppIds: Set<string>) => {
    setSelectedAppIds(newSelectedAppIds);
  };

  const handleItemsPerPageChange = (value: string) => {
    const newItemsPerPage = parseInt(value, 10);
    setItemsPerPage(newItemsPerPage);
    setCurrentPage(1); 
  };

  // Sidebar handlers
  const handleShowAppDetails = (appId: string, appName?: string) => {
    setDetailAppId(appId);
    setDetailAppName(appName);
  };

  const handleCloseAppDetails = () => {
    setDetailAppId(null);
    setDetailAppName(undefined);
  };

  // Debounced search handler
  const handleSearchChange = useDebouncedCallback((term: string) => {
    setSearchTerm(term);
    setCurrentPage(1); // Reset page when search term changes
  }, 300); // 300ms debounce

  // Filter change handlers that also reset page
  const handleFilterChange = (setter: React.Dispatch<React.SetStateAction<string>>, value: string) => {
      setter(value);
      setCurrentPage(1);
  };

  // Handler for capability checkbox change
  const handleCapabilityChange = (capability: OmiAppCapability, checked: boolean) => {
      setSelectedCapabilities(prev => {
          const next = new Set(prev);
          if (checked) {
              next.add(capability);
          } else {
              next.delete(capability);
          }
          return next;
      });
      setCurrentPage(1); // Reset page when capabilities filter changes
  };

  // Sort change handler
  const handleSortChange = (field: 'installs' | 'rating' | 'created' | null, direction: 'asc' | 'desc') => {
    setSortField(field);
    setSortDirection(direction);
    setCurrentPage(1); // Reset to first page when sorting changes
  };

  // --- Combined Loading and Error States ---
  const isLoading = isLoadingPublic || isLoadingUnapproved || isLoadingPrivate;
  // Show the first error encountered
  const error = errorPublic || errorUnapproved || errorPrivate; 
  // --- End Combined States ---

  return (
    <div className="space-y-10">
      <WelcomeOverview />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Apps Management</h1>
          <p className="text-muted-foreground mt-1">
            Monitor, and manage all Omi apps
          </p>
        </div>
      </div>

      {/* --- Filter Controls --- */}
      <div className="flex flex-col gap-4 rounded-md border p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
           {/* Status */}
          <div>
            <label htmlFor="status-filter" className="text-sm font-medium text-muted-foreground block mb-1">Status</label>
            <Select value={statusFilter} onValueChange={(value) => handleFilterChange(setStatusFilter, value)}>
              <SelectTrigger id="status-filter" className="h-9">
                <SelectValue placeholder="All Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="rejected">Rejected</SelectItem>
                <SelectItem value="under-review">Under Review</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {/* Privacy */}
          <div>
            <label htmlFor="privacy-filter" className="text-sm font-medium text-muted-foreground block mb-1">Privacy</label>
            <Select value={privacyFilter} onValueChange={(value) => handleFilterChange(setPrivacyFilter, value)}>
              <SelectTrigger id="privacy-filter" className="h-9">
                <SelectValue placeholder="All Apps" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Apps</SelectItem>
                <SelectItem value="public">Public</SelectItem>
                <SelectItem value="private">Private</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {/* Price */}
          <div>
            <label htmlFor="price-filter" className="text-sm font-medium text-muted-foreground block mb-1">Price</label>
            <Select value={priceFilter} onValueChange={(value) => handleFilterChange(setPriceFilter, value)}>
              <SelectTrigger id="price-filter" className="h-9">
                <SelectValue placeholder="All Apps" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Apps</SelectItem>
                <SelectItem value="free">Free</SelectItem>
                <SelectItem value="paid">Paid</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {/* Date Range */}
          <div>
            <label htmlFor="date-filter" className="text-sm font-medium text-muted-foreground block mb-1">Date Range</label>
            <Select value={dateFilter} onValueChange={(value) => handleFilterChange(setDateFilter, value)}>
              <SelectTrigger id="date-filter" className="h-9">
                <SelectValue placeholder="All Time" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Time</SelectItem>
                <SelectItem value="today">Today</SelectItem>
                <SelectItem value="week">This Week</SelectItem>
                <SelectItem value="month">This Month</SelectItem>
                <SelectItem value="year">This Year</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {/* Search Input */}
          <div className="lg:col-span-1 flex items-end">
            <Input
              placeholder="Search apps..."
              className="h-9 flex-1"
              onChange={(e) => handleSearchChange(e.target.value)}
              defaultValue={searchTerm} 
            />
          </div>
        </div>
        {/* Row 2: Capabilities Filter */}
        <div>
          <label className="text-sm font-medium text-muted-foreground block mb-2">Capabilities</label>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {ALL_CAPABILITIES.map((capability) => (
              <div key={capability} className="flex items-center space-x-2">
                <Checkbox 
                  id={`capability-${capability}`} 
                  checked={selectedCapabilities.has(capability)}
                  onCheckedChange={(checked) => handleCapabilityChange(capability, !!checked)}
                />
                <Label 
                  htmlFor={`capability-${capability}`} 
                  className="flex items-center gap-1.5 text-sm font-normal cursor-pointer"
                >
                  {getCapabilityIcon(capability, "h-3.5 w-3.5")} 
                  <span className="capitalize">{capability.replace(/_/g, ' ')}</span>
                </Label>
              </div>
            ))}
          </div>
        </div>
      </div>
       {/* --- End Filter Controls --- */}
      
      {/* Handle COMBINED loading and error states */} 
      {isLoading ? (
        <div className="flex items-center justify-center min-h-[300px]"><Spinner /></div>
      ) : error ? (
        // Display the first encountered error message
        <p className="text-destructive text-center py-4">Error loading apps: {(error as any)?.message || 'An unknown error occurred'}</p>
      ) : (
        // Pass the filtered and paginated apps to AppsList
        <AppsList 
          apps={currentApps} 
          selectedAppIds={selectedAppIds} 
          onSelectedAppIdsChange={handleSelectedAppIdsChange}
          onViewDetails={handleShowAppDetails}
          sortField={sortField}
          sortDirection={sortDirection}
          onSortChange={handleSortChange}
        /> 
      )}
      
      {/* Pagination Controls - use combined loading/error checks and totalFilteredApps */}
      {!isLoading && !error && totalPages > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4">
          {/* Items per page selector */} 
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
          
          {/* Page indicator and navigation */} 
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">
              {/* Update total apps count */} 
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
       {/* Show message if filters result in no apps */}
       {!isLoading && !error && totalFilteredApps === 0 && combinedApps.length > 0 && (
          <p className="text-center text-muted-foreground py-4">No apps match the current filters.</p>
        )}
         {/* Show message if NO apps were fetched at all (e.g., initial state or all fetches failed) */}
       {!isLoading && !error && combinedApps.length === 0 && (
           <p className="text-center text-muted-foreground py-4">No apps found.</p>
       ) }

      {/* App Detail Sidebar */}
      <AppDetailView 
        isOpen={!!detailAppId}
        onClose={handleCloseAppDetails}
        appDetails={null} // This will be handled by the useAppDetails hook inside AppDetailView
        appName={detailAppName}
        appId={detailAppId || undefined}
      />
    </div>
  );
}