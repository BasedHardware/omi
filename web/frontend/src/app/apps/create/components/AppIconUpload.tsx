import { Upload, Trash2 } from 'lucide-react';
import Image from 'next/image';
import { useState } from 'react';

interface AppIconUploadProps {
  appIcon: File | null;
  setAppIcon: (file: File | null) => void;
  appIconPreview: string | null;
  setAppIconPreview: (preview: string | null) => void;
}

export default function AppIconUpload({
  appIcon,
  setAppIcon,
  appIconPreview,
  setAppIconPreview
}: AppIconUploadProps) {

  const handleIconUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setAppIcon(file);

      const reader = new FileReader();
      reader.onload = (e) => {
        if (e.target?.result) {
          setAppIconPreview(e.target.result as string);
        }
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <div className="mb-4">
      <label htmlFor="app-icon-upload" className="mb-2 block text-sm font-medium text-gray-300">
        App Icon
      </label>
      <div className="flex items-center space-x-4">
        {appIconPreview ? (
          <div className="relative h-24 w-24 overflow-hidden rounded-xl border border-gray-700 shadow-md">
            <Image
              src={appIconPreview}
              alt="App Icon Preview"
              fill
              className="object-cover"
            />
            <button
              type="button"
              onClick={() => {
                setAppIcon(null);
                setAppIconPreview(null);
              }}
              className="absolute -right-1 -top-1 rounded-full bg-red-500 p-1.5 shadow-md transition-transform hover:scale-105"
            >
              <Trash2 className="h-3.5 w-3.5 text-white" />
            </button>
          </div>
        ) : (
          <div className="group h-24 w-24 cursor-pointer rounded-xl border border-dashed border-gray-700 bg-gray-800/50 p-2 shadow-sm transition-all hover:border-[#6C8EEF]/50 hover:bg-gray-800">
            <label htmlFor="app-icon-upload" className="flex h-full w-full cursor-pointer flex-col items-center justify-center">
              <Upload className="mb-1 h-6 w-6 text-gray-400 transition-colors group-hover:text-[#6C8EEF]" />
              <span className="text-xs text-gray-400 transition-colors group-hover:text-[#6C8EEF]">Upload Icon</span>
            </label>
          </div>
        )}
        <div className="text-sm text-gray-400">
          Upload a square image<br/>(recommended size: 512x512px)
        </div>
      </div>
      <input
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleIconUpload}
        id="app-icon-upload"
      />
    </div>
  );
}
