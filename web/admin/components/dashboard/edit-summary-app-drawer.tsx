'use client';

import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useAuth } from '@/components/auth-provider';
import { useAuthFetch } from '@/hooks/useAuthToken';
import { Loader2, Save, X } from 'lucide-react';
import { toast } from 'sonner';

interface EditSummaryAppDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  app: {
    id: string;
    name: string;
    description: string;
    memory_prompt?: string;
  } | null;
  onSave: () => void;
}

export function EditSummaryAppDrawer({ isOpen, onClose, app, onSave }: EditSummaryAppDrawerProps) {
  const { user } = useAuth();
  const { fetchWithAuth } = useAuthFetch();
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    memory_prompt: '',
  });
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (app) {
      setFormData({
        name: app.name || '',
        description: app.description || '',
        memory_prompt: app.memory_prompt || '',
      });
    }
  }, [app]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!app || !user) return;

    setIsLoading(true);
    try {
      const response = await fetchWithAuth('/api/omi/summary-apps', {
        method: 'PATCH',
        body: JSON.stringify({
          appId: app.id,
          name: formData.name,
          description: formData.description,
          memory_prompt: formData.memory_prompt,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to update app');
      }

      toast.success('App updated successfully');
      onSave();
      onClose();
    } catch (error: any) {
      console.error('Error updating app:', error);
      toast.error(error.message || 'Failed to update app');
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent className="sm:max-w-2xl w-full">
        <SheetHeader>
          <SheetTitle>Edit Summary App</SheetTitle>
          <SheetDescription>
            Update the app details for conversation summarization.
          </SheetDescription>
        </SheetHeader>
        
        <form onSubmit={handleSubmit} className="space-y-6 mt-6">
          <div className="space-y-2">
            <Label htmlFor="name">App Name</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              placeholder="Enter app name"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={formData.description}
              onChange={(e) => handleInputChange('description', e.target.value)}
              placeholder="Enter app description"
              rows={3}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="memory_prompt">Memory Prompt</Label>
            <Textarea
              id="memory_prompt"
              value={formData.memory_prompt}
              onChange={(e) => handleInputChange('memory_prompt', e.target.value)}
              placeholder="Enter memory prompt for conversation summarization"
              rows={4}
            />
          </div>

          <div className="flex justify-end space-x-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isLoading}
            >
              <X className="h-4 w-4 mr-2" />
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Save Changes
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}
