'use client';

import React, { useState, useMemo } from 'react';
import { useApps } from '@/hooks/useApps';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Search } from 'lucide-react';
import { OmiApp } from '@/lib/services/omi-api/types';

interface AddSummaryAppDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onAddApp: (appId: string) => Promise<void>;
  existingAppIds: string[];
}

export function AddSummaryAppDialog({
  isOpen,
  onClose,
  onAddApp,
  existingAppIds,
}: AddSummaryAppDialogProps) {
  const { apps, isLoading, error } = useApps();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Filter apps with memories capability and not already in summary apps
  const availableApps = useMemo(() => {
    if (!apps) return [];

    return apps.filter(
      (app) =>
        app.capabilities?.includes('memories') &&
        !existingAppIds.includes(app.id) &&
        (searchTerm === '' ||
          app.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          app.description?.toLowerCase().includes(searchTerm.toLowerCase()))
    );
  }, [apps, existingAppIds, searchTerm]);

  const handleSubmit = async () => {
    if (!selectedAppId) return;

    setIsSubmitting(true);
    try {
      await onAddApp(selectedAppId);
      setSelectedAppId(null);
      setSearchTerm('');
      onClose();
    } catch (err) {
      console.error('Error adding app:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setSelectedAppId(null);
    setSearchTerm('');
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Add Summary App</DialogTitle>
          <DialogDescription>
            Select an app with memory capability to add to the summary apps list.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
          {/* Search Input */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search apps..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Apps List */}
          <div className="flex-1 overflow-y-auto border rounded-md">
            {isLoading ? (
              <div className="flex items-center justify-center p-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : error ? (
              <p className="text-destructive text-center p-4">
                Error loading apps: {error.message}
              </p>
            ) : availableApps.length === 0 ? (
              <p className="text-center text-muted-foreground p-4">
                {searchTerm
                  ? 'No apps found matching your search.'
                  : 'No apps with memory capability available to add.'}
              </p>
            ) : (
              <div className="divide-y">
                {availableApps.map((app) => (
                  <div
                    key={app.id}
                    className={`p-4 cursor-pointer transition-colors hover:bg-accent ${
                      selectedAppId === app.id ? 'bg-accent' : ''
                    }`}
                    onClick={() => setSelectedAppId(app.id)}
                  >
                    <div className="flex items-start gap-3">
                      {app.image && (
                        <img
                          src={app.image}
                          alt={app.name}
                          className="w-10 h-10 rounded-md object-cover flex-shrink-0"
                        />
                      )}
                      <div className="flex-1 min-w-0">
                        <h4 className="font-semibold truncate">{app.name}</h4>
                        <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                          {app.description}
                        </p>
                        {app.memory_prompt && (
                          <p className="text-xs text-muted-foreground mt-2 line-clamp-1">
                            Memory: {app.memory_prompt}
                          </p>
                        )}
                      </div>
                      {selectedAppId === app.id && (
                        <div className="flex-shrink-0 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                          <svg
                            className="w-3 h-3 text-primary-foreground"
                            fill="none"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path d="M5 13l4 4L19 7"></path>
                          </svg>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!selectedAppId || isSubmitting}
          >
            {isSubmitting ? 'Adding...' : 'Add App'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
