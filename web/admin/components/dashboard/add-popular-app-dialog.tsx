"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Search, Plus, Loader2 } from "lucide-react";
import { OmiApp } from "@/lib/services/omi-api/types";
import { useApps } from "@/hooks/useApps";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/components/auth-provider";
import { useAuthFetch } from "@/hooks/useAuthToken";
import Image from "next/image";

interface AddPopularAppDialogProps {
  children: React.ReactNode;
  onAppAdded?: () => void;
}

export function AddPopularAppDialog({ children, onAppAdded }: AddPopularAppDialogProps) {
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);
  const { apps: allApps, isLoading, error, mutate } = useApps();
  const { toast } = useToast();
  const { user } = useAuth();
  const { fetchWithAuth } = useAuthFetch();

  // Filter apps based on search query, exclude already popular apps, and exclude persona apps
  const filteredApps = allApps?.filter((app) => {
    const matchesSearch = app.name.toLowerCase().includes(searchQuery.toLowerCase());
    const isNotPopular = app.is_popular !== true;
    const isNotPersona = !app.capabilities?.includes('persona');
    return matchesSearch && isNotPopular && isNotPersona;
  }) || [];

  const handleAddPopularApp = async (app: OmiApp) => {
    if (!user) {
      toast({
        title: "Error",
        description: "You must be logged in to perform this action.",
        variant: "destructive",
      });
      return;
    }

    setIsUpdating(true);
    try {
      // Call the API endpoint to mark app as popular
      const response = await fetchWithAuth(`/api/omi/apps/${app.id}/popular`, {
        method: 'PATCH',
        body: JSON.stringify({ value: true }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to mark app as popular');
      }

      const result = await response.json();

      // Show success toast
      toast({
        title: "Success",
        description: `${app.name} has been added to popular apps.`,
      });

      // Refresh the apps data
      if (mutate) {
        await mutate();
      }

      // Call the callback if provided
      if (onAppAdded) {
        onAppAdded();
      }

      // Close the dialog
      setOpen(false);
      setSearchQuery("");

    } catch (error) {
      console.error("Error adding app to popular apps:", error);
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to add app to popular apps. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px] max-h-[70vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Add Popular App</DialogTitle>
          <DialogDescription>
            Search and select an app to add to the popular apps section.
          </DialogDescription>
        </DialogHeader>
        
        <div className="flex-1 flex flex-col min-h-0">
          {/* Search Input */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search apps..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Apps List */}
          <div className="flex-1 overflow-y-auto space-y-2">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="text-center text-destructive py-4">
                Failed to load apps. {(error as any)?.message || 'Unknown error'}
              </div>
            ) : filteredApps.length === 0 ? (
              <div className="text-center text-muted-foreground py-8">
                {searchQuery ? "No apps found matching your search." : "No apps available to add."}
              </div>
            ) : (
              filteredApps.map((app) => (
                <Card key={app.id} className="hover:bg-muted/50 transition-colors">
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                          {app.image ? (
                            <div className="relative w-6 h-6">
                              <Image
                                src={app.image}
                                alt={`${app.name} logo`}
                                fill
                                sizes="24px"
                                className="object-contain rounded"
                                onError={(e) => {
                                  const target = e.target as HTMLImageElement;
                                  target.onerror = null;
                                  target.src = `https://via.placeholder.com/24`;
                                }}
                              />
                            </div>
                          ) : (
                            <span className="text-sm font-bold text-primary">
                              {app.name.charAt(0).toUpperCase()}
                            </span>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="font-medium truncate">{app.name}</h3>
                        </div>
                      </div>
                      <Button
                        size="sm"
                        onClick={() => handleAddPopularApp(app)}
                        disabled={isUpdating}
                        className="ml-2"
                      >
                        {isUpdating ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Plus className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
