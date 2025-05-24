'use client';

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ArrowLeft } from 'lucide-react';

interface SettingsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onReset: () => void;
}

export function SettingsDialog({
  isOpen,
  onClose,
  onReset
}: SettingsDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-black border-0 p-0 h-screen sm:h-auto sm:max-w-lg">
        <div className="fixed sm:absolute top-12 left-4 z-50">
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="text-white hover:text-gray-300 rounded-full h-12 w-12 flex items-center justify-center"
          >
            <ArrowLeft className="h-6 w-6" />
          </Button>
        </div>
        <div className="flex flex-col items-center justify-center min-h-[400px] px-4 pt-28 sm:pt-4">
          <div className="text-center mb-12">
            <h1 className="text-6xl font-serif mb-8 text-white">Settings</h1>
            <p className="text-gray-400">Manage your chat settings here</p>
          </div>
          <div className="w-full max-w-sm space-y-4">
            <Button
              onClick={onReset}
              className="w-full rounded-full bg-white text-black hover:bg-gray-200"
            >
              Reset Chat
            </Button>
            <Button
              variant="ghost"
              className="w-full rounded-full border border-red-500 text-red-500 hover:bg-red-500/10"
            >
              Flag for Removal
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
