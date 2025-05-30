'use client';

import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { ArrowLeft, BadgeCheck, Settings } from 'lucide-react';
import { FaLinkedin } from 'react-icons/fa';
import Link from 'next/link';

interface ChatHeaderProps {
  botName: string;
  botImage: string;
  username: string;
  botCategory: string;
  onBackClick: () => void;
  onSettingsClick: () => void;
  getStoreUrl: string;
}

export function ChatHeader({
  botName,
  botImage,
  username,
  botCategory,
  onBackClick,
  onSettingsClick,
  getStoreUrl
}: ChatHeaderProps) {
  return (
    <div className="flex items-center justify-between p-4 bg-zinc-900 border-b border-zinc-800">
      <Button variant="ghost" size="icon" onClick={onBackClick} className="text-white hover:text-gray-300">
        <ArrowLeft className="h-5 w-5" />
      </Button>
      <div className="flex items-center gap-2">
        {botCategory === 'linkedin' ? (
          <Link href={`https://www.linkedin.com/in/${username}`} target="_blank" rel="noopener noreferrer">
            <h2 className="text-lg font-semibold text-white truncate flex items-center hover:underline">
              {botName}
              <FaLinkedin className="ml-1 h-5 w-5 stroke-zinc-900" style={{ fill: '#0077b5' }} />
            </h2>
          </Link>
        ) : botCategory === 'twitter' ? (
          <Link href={`https://x.com/${username}`} target="_blank" rel="noopener noreferrer">
            <h2 className="text-lg font-semibold text-white truncate flex items-center hover:underline">
              {botName}
              <BadgeCheck className="ml-1 h-5 w-5 stroke-zinc-900" style={{ fill: '#00acee' }} />
            </h2>
          </Link>
        ) : botCategory === 'omi' ? (
          <Link href={getStoreUrl} target="_blank" rel="noopener noreferrer">
            <h2 className="text-lg font-semibold text-white truncate flex items-center hover:underline">
              {botName}
              <BadgeCheck className="ml-1 h-5 w-5 stroke-zinc-900" style={{ fill: '#00acee' }} />
            </h2>
          </Link>
        ) : null}
        <Avatar className="h-8 w-8">
          <AvatarImage src={botImage} alt={botName} />
          <AvatarFallback>{botName[0]}</AvatarFallback>
        </Avatar>
      </div>
      <Button variant="ghost" size="icon" className="text-white hover:text-gray-300" onClick={onSettingsClick}>
        <Settings className="h-5 w-5" />
      </Button>
    </div>
  );
}
