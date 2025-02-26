/**
 * @fileoverview ChatbotList Component for OMI Personas
 * @description Renders a searchable list of chatbot personas created from social media profiles
 * @author HarshithSunku
 * @license MIT
 */
import { Card, CardContent } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { BadgeCheck, Search } from 'lucide-react';
import { FaLinkedin } from 'react-icons/fa';
import { Chatbot } from '@/types/profiles';
import { Dispatch, SetStateAction, RefObject } from 'react';

interface ChatbotListProps {
  chatbots: Chatbot[];
  searchQuery: string;
  setSearchQuery: Dispatch<SetStateAction<string>>;
  handleChatbotClick: (bot: Chatbot) => void;
  hasMore: boolean;
  ref: RefObject<HTMLDivElement> | ((node?: Element | null) => void);
}

/**
 * ChatbotList Component
 * 
 * @component
 * @param {ChatbotListProps} props - Component props
 * @returns {JSX.Element} Rendered ChatbotList component
 */
export const ChatbotList = ({ chatbots, searchQuery, setSearchQuery, handleChatbotClick, hasMore, ref }: ChatbotListProps) => (
  <div className="w-full max-w-3xl">
    <div className="relative mb-6">
      <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-zinc-400 w-5 h-5" />
      <input
        type="text"
        placeholder="Search existing personas..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="w-full bg-zinc-900 text-white rounded-full py-2 pl-10 pr-4 focus:outline-none focus:ring-2 focus:ring-zinc-700 border-0"
      />
    </div>

    {chatbots.length > 0 ? (
      <div className="space-y-4">
        {chatbots.map(bot => (
          <Card
            key={bot.id}
            onClick={() => handleChatbotClick(bot)}
            className="hover:bg-zinc-800 transition-colors cursor-pointer bg-zinc-900 border-zinc-700"
          >
            <CardContent className="flex items-start space-x-4 p-4">
              <Avatar className="w-16 h-16 flex-shrink-0">
                <AvatarImage src={bot.avatar || '/omi-avatar.svg'} alt={bot.name} />
                <AvatarFallback>{bot.name[0]}</AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold text-white truncate flex items-center">
                    {bot.name}
                    {bot.category === 'linkedin' ? (
                      <FaLinkedin className="ml-1 h-5 w-5 stroke-zinc-900" style={{ fill: '#0077b5' }} />
                    ) : bot.category === 'twitter' ? (
                      <BadgeCheck className="ml-1 h-5 w-5 stroke-zinc-900" style={{ fill: '#00acee' }} />
                    ) : null}
                  </h2>
                  <span className="text-sm text-zinc-400 truncate">@{bot.username || bot.profile}</span>
                  {bot.category === 'linkedin' && bot.connection_count !== undefined && (
                    <span className="text-sm text-zinc-400">{bot.connection_count.toLocaleString()} connections</span>
                  )}
                  {bot.sub_count !== undefined && (
                    <span className="text-sm text-zinc-400">{bot.sub_count.toLocaleString()} followers</span>
                  )}
                </div>
                <p className="text-zinc-400 text-sm mt-1 line-clamp-2">{bot.profile || 'No profile available'}</p>
              </div>
            </CardContent>
          </Card>
        ))}

        {hasMore && (
          <div ref={ref} className="flex justify-center py-4">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
          </div>
        )}
      </div>
    ) : (
      <div className="text-center py-8">
        <p className="text-zinc-400">No matching personas found</p>
      </div>
    )}
  </div>
);
