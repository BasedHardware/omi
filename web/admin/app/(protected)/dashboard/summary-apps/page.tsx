'use client';

import React, { useState } from 'react';
import { useSummaryApps } from '@/hooks/useSummaryApps';
import { AppsList } from '@/components/dashboard/apps-list';
import { EditSummaryAppDrawer } from '@/components/dashboard/edit-summary-app-drawer';
import { AddSummaryAppDialog } from '@/components/dashboard/add-summary-app-dialog';
import { RemoveSummaryAppDialog } from '@/components/dashboard/remove-summary-app-dialog';
import { Button } from '@/components/ui/button';
import { Edit, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

export default function SummaryAppsPage() {
  const { summaryApps, isLoading, error, mutate, addSummaryApp, removeSummaryApp } = useSummaryApps();
  const [editingApp, setEditingApp] = useState<{
    id: string;
    name: string;
    description: string;
    memory_prompt?: string;
  } | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [removingApp, setRemovingApp] = useState<{ id: string; name: string } | null>(null);
  const [isRemoving, setIsRemoving] = useState(false);

  const handleEditApp = (app: any) => {
    setEditingApp({
      id: app.id,
      name: app.name || '',
      description: app.description || '',
      memory_prompt: app.memory_prompt || '',
    });
    setIsDrawerOpen(true);
  };

  const handleCloseDrawer = () => {
    setIsDrawerOpen(false);
    setEditingApp(null);
  };

  const handleSave = () => {
    mutate(); // Refresh the data
  };

  const handleAddApp = async (appId: string) => {
    try {
      await addSummaryApp(appId);
      toast.success('App added successfully');
      mutate(); // Refresh the list
    } catch (err: any) {
      toast.error(err?.message || 'Failed to add app');
      throw err;
    }
  };

  const handleRemoveApp = (app: any) => {
    setRemovingApp({ id: app.id, name: app.name });
  };

  const handleConfirmRemove = async () => {
    if (!removingApp) return;

    setIsRemoving(true);
    try {
      await removeSummaryApp(removingApp.id);
      toast.success('App removed successfully');
      mutate(); // Refresh the list
      setRemovingApp(null);
    } catch (err: any) {
      toast.error(err?.message || 'Failed to remove app');
    } finally {
      setIsRemoving(false);
    }
  };

  // Custom render function for each app item with edit and remove buttons
  const renderAppItem = (app: any) => (
    <div key={app.id} className="flex items-center justify-between p-4 border rounded-lg">
      <div className="flex-1">
        <h3 className="font-semibold">{app.name}</h3>
        <p className="text-sm text-muted-foreground mt-1">{app.description}</p>
        {app.memory_prompt && (
          <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
            Memory: {app.memory_prompt}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 ml-4">
        <Button
          variant="outline"
          size="sm"
          onClick={() => handleEditApp(app)}
        >
          <Edit className="h-4 w-4 mr-2" />
          Edit
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => handleRemoveApp(app)}
          className="text-destructive hover:text-destructive"
        >
          <Trash2 className="h-4 w-4 mr-2" />
          Remove
        </Button>
      </div>
    </div>
  );

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Summary Apps</h1>
          <p className="text-muted-foreground mt-1">Manage conversation summarisation default apps</p>
        </div>
        <Button onClick={() => setIsAddDialogOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add App
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : error ? (
        <p className="text-destructive text-center py-4">Error: {(error as any)?.message || 'Failed to load'}</p>
      ) : !summaryApps || summaryApps.length === 0 ? (
        <p className="text-center text-muted-foreground py-4">No summary apps configured.</p>
      ) : (
        <div className="space-y-4">
          {summaryApps.map(renderAppItem)}
        </div>
      )}

      <EditSummaryAppDrawer
        isOpen={isDrawerOpen}
        onClose={handleCloseDrawer}
        app={editingApp}
        onSave={handleSave}
      />

      <AddSummaryAppDialog
        isOpen={isAddDialogOpen}
        onClose={() => setIsAddDialogOpen(false)}
        onAddApp={handleAddApp}
        existingAppIds={summaryApps?.map((app) => app.id) || []}
      />

      <RemoveSummaryAppDialog
        isOpen={!!removingApp}
        onClose={() => setRemovingApp(null)}
        onConfirm={handleConfirmRemove}
        appName={removingApp?.name || ''}
        isRemoving={isRemoving}
      />
    </div>
  );
}


