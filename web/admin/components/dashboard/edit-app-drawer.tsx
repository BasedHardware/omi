'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import type { OmiApp } from '@/lib/services/omi-api/types';
import { useAuthFetch } from '@/hooks/useAuthToken';
import { Loader2, Save, UploadCloud } from 'lucide-react';
import { toast } from 'sonner';

interface EditAppDrawerProps {
  open: boolean;
  onClose: () => void;
  app: OmiApp | null;
  onSaved?: () => void;
}

export function EditAppDrawer({ open, onClose, app, onSaved }: EditAppDrawerProps) {
  const { fetchWithAuth } = useAuthFetch();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [memoryPrompt, setMemoryPrompt] = useState('');
  const [chatPrompt, setChatPrompt] = useState('');
  const [personaPrompt, setPersonaPrompt] = useState('');
  const [selectedThumb, setSelectedThumb] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const hasMemories = useMemo(() => !!app?.capabilities?.includes('memories' as any), [app]);
  const hasChat = useMemo(() => !!app?.capabilities?.includes('chat' as any), [app]);
  const hasPersona = useMemo(() => !!app?.capabilities?.includes('persona' as any), [app]);

  useEffect(() => {
    if (!app) return;
    setName(app.name || '');
    setDescription(app.description || '');
    setImageUrl(app.image || '');
    setMemoryPrompt(app.memory_prompt || '');
    setChatPrompt(app.chat_prompt || '');
    setPersonaPrompt(app.persona_prompt || '');
    setSelectedThumb(null);
    setFile(null);
  }, [app]);

  const effectiveImagePreview = useMemo(() => {
    if (file) return URL.createObjectURL(file);
    if (selectedThumb) return selectedThumb;
    if (imageUrl) return imageUrl;
    return '';
  }, [file, selectedThumb, imageUrl]);

  const resetLocal = () => {
    setSelectedThumb(null);
    setFile(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    if (f) setSelectedThumb(null);
  };

  const handleThumbPick = (url: string) => {
    setSelectedThumb(url);
    setFile(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!app) return;
    setSubmitting(true);
    try {
      const form = new FormData();
      form.append('app_id', app.id);
      form.append('uid', app.uid);
      if (name) form.append('name', name);
      if (description) form.append('description', description);
      if (hasMemories && memoryPrompt) form.append('memory_prompt', memoryPrompt);
      if (hasChat && chatPrompt) form.append('chat_prompt', chatPrompt);
      if (hasPersona && personaPrompt) form.append('persona_prompt', personaPrompt);

      // Image precedence: uploaded file > picked thumbnail > typed URL
      if (file) {
        form.append('image', file);
      } else if (selectedThumb) {
        form.append('image_url', selectedThumb);
      } else if (imageUrl) {
        form.append('image_url', imageUrl);
      }

      const res = await fetchWithAuth(`/api/omi/apps/${app.id}/update`, {
        method: 'POST',
        body: form,
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error((data && (data.error || data.message)) || 'Failed to update app');
      }

      toast.success('App updated');
      onSaved?.();
      onClose();
      resetLocal();
    } catch (err: any) {
      toast.error(err?.message || 'Update failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="sm:max-w-2xl w-full">
        <SheetHeader>
          <SheetTitle>Edit App</SheetTitle>
          <SheetDescription>Update app details and image.</SheetDescription>
        </SheetHeader>

        {app && (
          <form onSubmit={handleSubmit} className="space-y-6 mt-6">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea id="description" rows={4} value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>

            {hasMemories && (
              <div className="space-y-2">
                <Label htmlFor="memory_prompt">Memory Prompt</Label>
                <Textarea id="memory_prompt" rows={3} value={memoryPrompt} onChange={(e) => setMemoryPrompt(e.target.value)} />
              </div>
            )}

            {hasChat && (
              <div className="space-y-2">
                <Label htmlFor="chat_prompt">Chat Prompt</Label>
                <Textarea id="chat_prompt" rows={3} value={chatPrompt} onChange={(e) => setChatPrompt(e.target.value)} />
              </div>
            )}

            {hasPersona && (
              <div className="space-y-2">
                <Label htmlFor="persona_prompt">Persona Prompt</Label>
                <Textarea id="persona_prompt" rows={3} value={personaPrompt} onChange={(e) => setPersonaPrompt(e.target.value)} />
              </div>
            )}

            <div className="space-y-3">
              <Label>Image</Label>
              <div className="flex items-start gap-4">
                <div className="w-28 h-28 rounded-md border overflow-hidden bg-muted flex items-center justify-center">
                  {effectiveImagePreview ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={effectiveImagePreview} alt="preview" className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-xs text-muted-foreground">No image</span>
                  )}
                </div>
                <div className="flex-1 space-y-2">
                  <Input
                    placeholder="https://..."
                    value={imageUrl}
                    onChange={(e) => {
                      setImageUrl(e.target.value);
                      setSelectedThumb(null);
                      setFile(null);
                    }}
                  />
                  <div className="flex items-center gap-2">
                    <Input type="file" accept="image/*" onChange={handleFileChange} />
                    {file && <span className="text-xs text-muted-foreground">{file.name}</span>}
                  </div>
                </div>
              </div>

              {Array.isArray(app.thumbnail_urls) && app.thumbnail_urls.length > 0 && (
                <div className="grid grid-cols-4 gap-2">
                  {app.thumbnail_urls.map((url) => (
                    <button
                      key={url}
                      type="button"
                      className={`relative rounded-md overflow-hidden border ${selectedThumb === url ? 'ring-2 ring-primary' : ''}`}
                      onClick={() => handleThumbPick(url)}
                      title="Pick thumbnail"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={url} alt="thumb" className="w-full h-20 object-cover" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                Save
              </Button>
            </div>
          </form>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default EditAppDrawer;


