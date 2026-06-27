'use client';

import React, { useRef, useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Upload, X, Loader2 } from 'lucide-react';
import { isValidImage, isValidFileSize } from '@/lib/utils/upload';
import { toast } from 'sonner';

interface ImageUploadProps {
  value: string;
  onChange: (url: string) => void;
  onFileSelect?: (file: File | null) => void;
  pendingFile?: File | null;
  label?: string;
  placeholder?: string;
  disabled?: boolean;
}

export function ImageUpload({
  value,
  onChange,
  onFileSelect,
  pendingFile,
  label = 'Image',
  placeholder = 'https://... or upload',
  disabled = false,
}: ImageUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);

  // Create local preview URL for pending file
  useEffect(() => {
    if (pendingFile) {
      const url = URL.createObjectURL(pendingFile);
      setLocalPreview(url);
      return () => URL.revokeObjectURL(url);
    } else {
      setLocalPreview(null);
    }
  }, [pendingFile]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!isValidImage(file)) {
      toast.error('Please select a valid image (JPEG, PNG, GIF, or WebP)');
      return;
    }

    if (!isValidFileSize(file, 5)) {
      toast.error('Image must be less than 5MB');
      return;
    }

    // Store file for later upload, clear any existing URL
    if (onFileSelect) {
      onFileSelect(file);
      onChange(''); // Clear URL since we have a pending file
    }

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleClear = () => {
    onChange('');
    if (onFileSelect) {
      onFileSelect(null);
    }
    setLocalPreview(null);
  };

  const handleUrlChange = (url: string) => {
    onChange(url);
    // Clear pending file if user types a URL
    if (url && onFileSelect) {
      onFileSelect(null);
    }
  };

  const previewUrl = localPreview || value;
  const hasContent = previewUrl || pendingFile;

  return (
    <div className="space-y-2">
      {label && <Label>{label}</Label>}
      <div className="flex gap-2">
        <Input
          placeholder={placeholder}
          value={value}
          onChange={(e) => handleUrlChange(e.target.value)}
          className="flex-1"
          disabled={disabled || !!pendingFile}
        />
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          accept="image/jpeg,image/png,image/gif,image/webp"
          className="hidden"
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          title="Upload image"
        >
          <Upload className="h-4 w-4" />
        </Button>
        {hasContent && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={handleClear}
            disabled={disabled}
            title="Clear"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
      {pendingFile && (
        <p className="text-xs text-muted-foreground">
          📎 {pendingFile.name} (will upload on save)
        </p>
      )}
      {previewUrl && (
        <div className="mt-2 relative rounded-md border overflow-hidden bg-muted/50 w-fit">
          <img
            src={previewUrl}
            alt="Preview"
            className="max-h-32 max-w-full object-contain"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        </div>
      )}
    </div>
  );
}
