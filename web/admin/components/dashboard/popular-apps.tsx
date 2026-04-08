"use client";

import { Star, ArrowRight, Loader2, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { OmiApp } from "@/lib/services/omi-api/types";
import { useApps } from "@/hooks/useApps";
import Image from "next/image";
import { Card, CardContent } from "@/components/ui/card";
import { AddPopularAppDialog } from "./add-popular-app-dialog";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/components/auth-provider";
import { useAuthFetch } from "@/hooks/useAuthToken";
import { useState } from "react";

export function PopularApps() {
  const { apps: allApps, isLoading, error, mutate } = useApps();
  const { toast } = useToast();
  const { user } = useAuth();
  const { fetchWithAuth } = useAuthFetch();
  const [removingAppId, setRemovingAppId] = useState<string | null>(null);

  const popularApps = allApps?.filter((app) => app.is_popular === true) || [];

  const handleRemovePopularApp = async (app: OmiApp, event: React.MouseEvent) => {
    event.stopPropagation(); // Prevent navigation to app details
    
    if (!user) {
      toast({
        title: "Error",
        description: "You must be logged in to perform this action.",
        variant: "destructive",
      });
      return;
    }

    setRemovingAppId(app.id);
    try {
      // Call the API endpoint to remove app from popular
      const response = await fetchWithAuth(`/api/omi/apps/${app.id}/popular`, {
        method: 'PATCH',
        body: JSON.stringify({ value: false }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to remove app from popular apps');
      }

      // Show success toast
      toast({
        title: "Success",
        description: `${app.name} has been removed from popular apps.`,
      });

      // Refresh the apps data
      if (mutate) {
        await mutate();
      }

    } catch (error) {
      console.error("Error removing app from popular apps:", error);
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to remove app from popular apps. Please try again.",
        variant: "destructive",
      });
    } finally {
      setRemovingAppId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center text-destructive py-4">
        Failed to load popular apps. {(error as any)?.message || 'Unknown error'}
      </div>
    );
  }
  
  if (popularApps.length === 0) {
     return (
      <div className="text-center text-muted-foreground py-10">
        No popular apps found.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <Star className="h-5 w-5 text-yellow-500 fill-yellow-500" />
        <h2 className="text-xl font-semibold">Popular Apps</h2>
      </div>
      
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {popularApps.map((app) => (
          <Card 
            key={app.id}
            className="flex flex-col items-center justify-center p-4 aspect-square text-center hover:bg-muted/50 transition-colors group relative"
          >
            {/* Remove button */}
            <Button
              variant="ghost"
              size="sm"
              className="absolute top-1 right-1 h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive hover:text-destructive-foreground"
              onClick={(e) => handleRemovePopularApp(app, e)}
              disabled={removingAppId === app.id}
            >
              {removingAppId === app.id ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <X className="h-3 w-3" />
              )}
            </Button>

            <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-3 flex-shrink-0">
              {app.image ? (
                <div className="relative w-8 h-8">
                  <Image
                    src={app.image || `https://via.placeholder.com/32`}
                    alt={`${app.name} logo`}
                    fill
                    sizes="32px"
                    className="object-contain rounded"
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      target.onerror = null;
                      target.src = `https://via.placeholder.com/32`;
                    }}
                  />
                </div>
              ) : (
                <span className="text-xl font-bold text-primary">
                  {app.name.charAt(0).toUpperCase()}
                </span>
              )}
            </div>
            <p className="text-sm font-medium truncate w-full">{app.name}</p>
          </Card>
        ))}

        <AddPopularAppDialog>
          <Card className="flex flex-col items-center justify-center p-4 aspect-square text-center border-dashed border-muted-foreground/50 hover:border-primary hover:bg-muted/30 transition-colors cursor-pointer group">
            <div className="w-12 h-12 rounded-lg bg-muted/50 flex items-center justify-center mb-3">
              <Plus className="h-6 w-6 text-muted-foreground group-hover:text-primary" />
            </div>
            <p className="text-sm font-medium text-muted-foreground group-hover:text-primary">Add Popular App</p>
          </Card>
        </AddPopularAppDialog>
      </div>
    </div>
  );
}