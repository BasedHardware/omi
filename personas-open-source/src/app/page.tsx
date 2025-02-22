'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { db } from '@/lib/firebase';
import { collection, addDoc, query, where, getDocs, orderBy, startAfter, limit } from 'firebase/firestore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Search, Plus, BadgeCheck } from 'lucide-react';
import { FaDiscord } from 'react-icons/fa';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Card, CardContent } from '@/components/ui/card';
import { toast } from 'sonner';
import { PreorderBanner } from '@/components/shared/PreorderBanner';
import { Mixpanel } from '@/lib/mixpanel';
import { useInView } from 'react-intersection-observer';
import { TwitterProfile } from '@/types/twitter';

type Chatbot = {
  id: string;
  username?: string;
  profile?: string;
  avatar: string;
  desc: string;
  name: string;
  sub_count?: number;
  category: string;
  created_at?: string;
  verified?: boolean;
};

const formatTwitterAvatarUrl = (url: string): string => {
  if (!url) return '/omi-avatar.svg';
  let formattedUrl = url.replace('http://', 'https://');
  formattedUrl = formattedUrl.replace('_normal', '');
  if (formattedUrl.includes('pbs.twimg.com')) {
    formattedUrl = formattedUrl.replace('/profile_images/', '/profile_images/');
  }
  return formattedUrl;
};

const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
    hour12: false,
  }).format(date).replace(',', ' at');
};

const fetchTwitterTimeline = async (screenname: string) => {
  try {
    const response = await fetch(`https://${process.env.NEXT_PUBLIC_RAPIDAPI_HOST}/timeline.php?screenname=${screenname}`, {
      headers: {
        'x-rapidapi-key': process.env.NEXT_PUBLIC_RAPIDAPI_KEY!,
        'x-rapidapi-host': process.env.NEXT_PUBLIC_RAPIDAPI_HOST!,
      },
    });

    const data = await response.json();

    const tweets = [];
    if (data.timeline) {
      for (const tweet of Object.values(data.timeline)) {
        const tweetData = tweet as any;
        if (tweets.length >= 30) break;
        if (tweetData.text && !tweetData.text.startsWith('RT @')) {
          tweets.push(tweetData.text);
        }
      }
    }

    return tweets;
  } catch (error) {
    console.error('Error fetching timeline:', error);
    return [];
  }
};

export default function HomePage() {
  const router = useRouter();
  const [chatbots, setChatbots] = useState<Chatbot[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [twitterHandle, setTwitterHandle] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [lastDoc, setLastDoc] = useState<any>(null);
  const { ref, inView } = useInView();

  const BOTS_PER_PAGE = 50;

  useEffect(() => {
    // Identify the user first
    Mixpanel.identify();

    // Then track the page view
    Mixpanel.track('Page View', {
      page: 'Home',
      url: window.location.pathname,
      timestamp: new Date().toISOString()
    });
  }, []);

  const fetchChatbots = async (isInitial = true) => {
    try {
      const chatbotsCollection = collection(db, 'plugins_data');
      let q = query(
        chatbotsCollection,
        where('category', '==', 'twitter'),
        orderBy('sub_count', 'desc')
      );

      if (!isInitial && lastDoc) {
        q = query(q, startAfter(lastDoc), limit(BOTS_PER_PAGE));
      } else {
        q = query(q, limit(BOTS_PER_PAGE));
      }

      const querySnapshot = await getDocs(q);

      // Single Map for all bots, keyed by lowercase username
      const allBotsMap = new Map();

      // Process all docs
      querySnapshot.docs.forEach(doc => {
        const bot = { id: doc.id, ...doc.data() } as Chatbot;
        // Normalize username
        const normalizedUsername = bot.username?.toLowerCase().trim();

        if (!normalizedUsername || !bot.name) return;

        const existingBot = allBotsMap.get(normalizedUsername);
        // Only update if we don't have this bot or if this version has more followers
        if (!existingBot || (bot.sub_count || 0) > (existingBot.sub_count || 0)) {
          allBotsMap.set(normalizedUsername, bot);
        }
      });

      const uniqueBots = Array.from(allBotsMap.values());

      if (isInitial) {
        setChatbots(uniqueBots);
      } else {
        setChatbots(prev => {
          const masterMap = new Map();

          // First add existing bots to master map
          prev.forEach(bot => {
            const username = bot.username?.toLowerCase().trim();
            if (username) {
              masterMap.set(username, bot);
            }
          });

          // Then add new bots, only if they have higher sub_count
          uniqueBots.forEach(bot => {
            const username = bot.username?.toLowerCase().trim();
            if (username) {
              const existing = masterMap.get(username);
              if (!existing || (bot.sub_count || 0) > (existing.sub_count || 0)) {
                masterMap.set(username, bot);
              }
            }
          });

          // Convert back to array and sort by sub_count
          return Array.from(masterMap.values())
            .sort((a, b) => (b.sub_count || 0) - (a.sub_count || 0));
        });
      }

      setLastDoc(querySnapshot.docs[querySnapshot.docs.length - 1]);
      setHasMore(querySnapshot.docs.length === BOTS_PER_PAGE);
    } catch (error: any) {
      console.error('Error fetching chatbots:', error);
      setError('Failed to load chatbots.');
      toast.error('Failed to load chatbots.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChatbots();

  }, []);

  useEffect(() => {
    if (inView && hasMore && !loading) {
      fetchChatbots(false);
    }
  }, [inView]);

  const handleChatbotClick = (bot: Chatbot) => {
    router.push(`/chat?id=${encodeURIComponent(bot.id)}`);
  };

  const filteredChatbots = chatbots.filter(bot =>
    bot.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (bot.username && bot.username.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const fetchTwitterProfile = async () => {
    if (!twitterHandle) return;

    const cleanHandle = twitterHandle.replace('@', '');

    setIsCreating(true);
    try {
      const q = query(
        collection(db, 'plugins_data'),
        where('username', '==', cleanHandle.toLowerCase())
      );
      const querySnapshot = await getDocs(q);

      if (!querySnapshot.empty) {
        const existingDoc = querySnapshot.docs[0];
        toast.success('Profile already exists, redirecting...');
        router.push(`/chat?id=${existingDoc.id}`);
        return;
      }

      const profileResponse = await fetch(`https://${process.env.NEXT_PUBLIC_RAPIDAPI_HOST}/screenname.php?screenname=${cleanHandle}`, {
        headers: {
          'x-rapidapi-key': process.env.NEXT_PUBLIC_RAPIDAPI_KEY!,
          'x-rapidapi-host': process.env.NEXT_PUBLIC_RAPIDAPI_HOST!,
        },
      });

      const profileData: TwitterProfile = await profileResponse.json();

      const recentTweets = await fetchTwitterTimeline(cleanHandle);

      const formattedAvatarUrl = formatTwitterAvatarUrl(profileData.avatar);

      const enhancedDesc = `${profileData.desc || 'No description available'}\n\nHere are my recent tweets:\n${recentTweets.join('\n')}`;

      const extraPromptRules = process.env.NEXT_PUBLIC_EXTRA_PROMPT_RULES ?? "";

      const fullChatPrompt = `You are ${profileData.name} AI, you must personify ${profileData.name} as well as you can.

Style:
- Interactive highly opinionated messages and questions.
- Reference your tweets naturally

Rules:
- Never mention being AI
- No ** or formal language
- 2-3 sentences for response. Never more than 20 words.
- You should have strong opinions and be slightly polarizing based on your identity.
- You must make the conversation flow. You excel at coherent conversations.
${extraPromptRules}

Recent activity on Twitter:\n"${enhancedDesc}" which you can use for your personality. Responses should help the conversation go deeper. You have strong opinions, slightly controversial.`;


      try {
        const createdAtFormatted = formatDate(new Date().toISOString());
        const docRef = await addDoc(collection(db, 'plugins_data'), {
          username: cleanHandle.toLowerCase().replace('@', ''),
          avatar: formattedAvatarUrl,
          profile: profileData.desc || 'No description available',
          desc: enhancedDesc,
          name: profileData.name,
          sub_count: profileData.sub_count || 0,
          category: 'twitter',
          created_at: createdAtFormatted,
          chat_prompt: fullChatPrompt,
        });

        toast.success('Profile saved successfully!');

        router.push(`/chat?id=${docRef.id}`);
      } catch (firebaseError) {
        console.error('Firebase error:', firebaseError);
        toast.error('Failed to save profile');
      }

    } catch (error) {
      console.error('Error fetching Twitter profile:', error);
      toast.error('Failed to fetch Twitter profile');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-white">
      <PreorderBanner botName="your favorite personal" />
      {/* Header */}
      <div className="p-4 border-b border-zinc-800">
        <div className="flex items-center justify-between max-w-3xl mx-auto">
          <Link href="https://www.omi.me/products/friend-dev-kit-2?ref=personas&utm_source=personas.omi.me&utm_campaign=personas_top_banner" target="_blank">
            <img src="/omilogo.png" alt="Logo" className="h-6" />
          </Link>
          <Link
            href="https://www.omi.me/products/friend-dev-kit-2?ref=personas&utm_source=personas.omi.me&utm_campaign=personas_top_banner"
            target="_blank"
            className="bg-white hover:bg-gray-200 text-black px-4 py-2 rounded-full flex items-center"
          >
            <span className="mr-1">Take AI personas with you</span>
            <span className="text-lg">↗</span>
          </Link>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex flex-col items-center px-4 py-8 md:py-16">
        {/* Create Section */}
        <div className="text-center max-w-md mx-auto">
          <h1 className="text-4xl md:text-5xl font-serif mb-3 md:mb-4">AI personas</h1>
          <p className="text-gray-400 text-sm md:text-base mb-8 md:mb-12">
            Create new AI Twitter personalities
          </p>
        </div>

        {/* Input Area */}
        <div className="w-full max-w-sm space-y-4 mb-12 md:mb-16">
          <Input
            type="text"
            placeholder="Enter Twitter handle (e.g., @elonmusk)..."
            value={twitterHandle}
            onChange={(e) => setTwitterHandle(e.target.value)}
            className="rounded-full bg-gray-800 text-white border-gray-700 focus:border-gray-600"
          />
          <Button
            className="w-full rounded-full bg-white text-black hover:bg-gray-200"
            onClick={fetchTwitterProfile}
            disabled={isCreating}
          >
            {isCreating ? 'Creating...' : 'Create AI Persona'}
          </Button>
        </div>

        {/* Chatbot List */}
        {!loading && filteredChatbots.length > 0 && (
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

            <div className="space-y-4">
              {filteredChatbots.map(bot => (
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
                          <BadgeCheck
                            className="ml-1 h-5 w-5 stroke-zinc-900"
                            style={{ fill: '#00acee' }}
                          />
                        </h2>
                        <span className="text-sm text-zinc-400 truncate">
                          @{bot.username || bot.profile}
                        </span>
                        {bot.sub_count !== undefined && (
                          <span className="text-sm text-zinc-400">
                            {bot.sub_count.toLocaleString()} followers
                          </span>
                        )}
                      </div>
                      <p className="text-zinc-400 text-sm mt-1 line-clamp-2">
                        {bot.profile || 'No profile available'}
                      </p>
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
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="max-w-4xl mx-auto px-4 py-4">
        <div className="flex flex-col sm:flex-row justify-between text-xs text-zinc-400">
          <span className="mb-2 sm:mb-0 sm:mr-8">Omi by Based Hardware © 2025</span>
          <div className="flex gap-2">
            <Button variant="link" className="p-0 h-auto text-xs text-zinc-400 hover:text-white">Terms & Conditions</Button>
            <Button variant="link" className="p-0 h-auto text-xs text-zinc-400 hover:text-white">Privacy Policy</Button>
          </div>
        </div>
      </footer>
    </div>
  );
}

