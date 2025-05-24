'use client';

import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Message } from '@/types/chat';
import { RefObject } from 'react';

interface ChatMessagesProps {
  messages: Message[];
  typingMessage: Message | null;
  botName: string;
  botImage: string;
  scrollRef: RefObject<HTMLDivElement>;
}

export function ChatMessages({
  messages,
  typingMessage,
  botName,
  botImage,
  scrollRef
}: ChatMessagesProps) {
  return (
    <ScrollArea className="flex-grow p-4" ref={scrollRef}>
      <div className="space-y-4 max-w-4xl mx-auto">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {message.sender === 'omi' && (
              <Avatar className="h-8 w-8 mr-2">
                <AvatarImage src={botImage} alt={botName} />
                <AvatarFallback>{botName[0]}</AvatarFallback>
              </Avatar>
            )}
            <div
              className={`max-w-[80%] rounded-3xl p-4 ${
                message.sender === 'user'
                  ? 'bg-white text-zinc-800'
                  : 'bg-zinc-800 text-white'
              }`}
            >
              <p className="text-sm">{message.text}</p>
            </div>
          </div>
        ))}
        {typingMessage && (
          <div className="flex justify-start">
            <Avatar className="h-8 w-8 mr-2">
              <AvatarImage src={botImage} alt={botName} />
              <AvatarFallback>{botName[0]}</AvatarFallback>
            </Avatar>
            <div className="max-w-[80%] rounded-3xl p-4 bg-zinc-800 text-white">
              <p className="text-sm">{typingMessage.text}</p>
            </div>
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
