'use client';

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send } from 'lucide-react';
import Link from 'next/link';
import { RefObject } from 'react';

interface ChatInputProps {
  inputRef: RefObject<HTMLInputElement>;
  inputText: string;
  isLoading: boolean;
  onInputChange: (value: string) => void;
  onSendMessage: () => void;
  onKeyPress: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  getStoreUrl: string;
}

export function ChatInput({
  inputRef,
  inputText,
  isLoading,
  onInputChange,
  onSendMessage,
  onKeyPress,
  getStoreUrl
}: ChatInputProps) {
  return (
    <div className="p-4 pb-16 sm:pb-4 border-t border-zinc-800">
      <div className="max-w-4xl mx-auto flex gap-2">
        <Input
          ref={inputRef}
          type="text"
          placeholder="Type your message..."
          value={inputText}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyPress={onKeyPress}
          className="flex-grow rounded-full bg-zinc-800 border-0 text-white placeholder-gray-400"
          disabled={isLoading}
        />
        <Button
          variant="ghost"
          size="icon"
          className="rounded-full text-white hover:text-gray-300"
          onClick={onSendMessage}
          disabled={isLoading}
        >
          <Send className="h-5 w-5" />
        </Button>
      </div>
      
      <div className="flex justify-center mt-5 mb-6 sm:mb-2">
        <Button
          onClick={() => window.open(getStoreUrl, '_blank')}
          className="w-full max-w-[250px] py-5 text-base font-bold text-[16px] rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white hover:opacity-90 shadow-lg"
        >
          Train AI on Your Real Life!
        </Button>
      </div>
      
      <div className="max-w-4xl mx-auto mt-4">
        <div className="flex flex-col sm:flex-row justify-between text-xs text-gray-500">
          <div className="flex gap-2 mb-2 sm:mb-0">
            <span>Omi by Based Hardware © 2025</span>
          </div>
          <div className="flex gap-2">
            <Button variant="link" className="p-0 h-auto text-xs text-gray-500 hover:text-white">
              Terms & Conditions
            </Button>
            <Link href="https://www.omi.me/pages/privacy" target="_blank" rel="noopener noreferrer">
              <Button variant="link" className="p-0 h-auto text-xs text-gray-500 hover:text-white">
                Privacy Policy
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}