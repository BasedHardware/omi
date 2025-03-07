'use client';

import { SetStateAction, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { db } from '@/lib/firebase';
import { collection, addDoc, query, where, getDocs, orderBy, startAfter, limit, doc, setDoc, or } from 'firebase/firestore';
import { toast } from 'sonner';
import { Mixpanel } from '@/lib/mixpanel';
import { useInView } from 'react-intersection-observer';
import { ulid } from 'ulid';
import { auth } from '@/lib/firebase';
import { Header } from '@/components/Header';
import { InputArea } from '@/components/InputArea';
import { ChatbotList } from '@/components/ChatbotList';
import { Footer } from '@/components/Footer';
import { Chatbot, TwitterProfile, LinkedinProfile } from '@/types/profiles';
import { PreorderBanner } from '@/components/shared/PreorderBanner';

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

const PlatformSelectionModal = ({
  isOpen,
  onClose,
  platforms,
  onSelect,
  mode,
}: {
  isOpen: boolean;
  onClose: () => void;
  platforms: { twitter: boolean; linkedin: boolean };
  onSelect: (platform: 'twitter' | 'linkedin') => void;
  mode: 'create' | 'add';
}) => (
  <div className={`fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center ${isOpen ? '' : 'hidden'}`}>
    <div className="bg-zinc-900 p-6 rounded-lg max-w-md w-full">
      <h2 className="text-xl font-bold mb-4">
        {mode === 'create' ? 'Select Platform' : 'Add Additional Profile'}
      </h2>
      <p className="text-zinc-400 mb-6">
        {mode === 'create'
          ? 'This handle is available on multiple platforms. Which one would you like to use?'
          : 'We found an additional profile for this handle. Would you like to add it?'}
      </p>
      <div className="space-y-4">
        {platforms.twitter && (
          <button
            onClick={() => onSelect('twitter')}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg"
          >
            Twitter Profile
          </button>
        )}
        {platforms.linkedin && (
          <button
            onClick={() => onSelect('linkedin')}
            className="w-full flex items-center justify-center gap-2 bg-[#0077b5] hover:bg-[#006399] text-white py-2 rounded-lg"
          >
            LinkedIn Profile
          </button>
        )}
        <button onClick={onClose} className="w-full text-zinc-400 hover:text-white">
          Cancel
        </button>
      </div>
    </div>
  </div>
);

export default function HomePage() {
  const router = useRouter();
  const [chatbots, setChatbots] = useState<Chatbot[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isCreating, setIsCreating] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [lastDoc, setLastDoc] = useState<any>(null);
  const { ref, inView } = useInView();
  const [handle, setHandle] = useState('');
  //modal state variables
  const [showPlatformModal, setShowPlatformModal] = useState(false);
  const [pendingCleanHandle, setPendingCleanHandle] = useState<string | null>(null);
  const [availablePlatforms] = useState({ twitter: true, linkedin: true });
  const [platformSelectionMode] = useState<'create' | 'add'>('create');

  const handleInputChange = (e: { target: { value: SetStateAction<string>; }; }) => {
    setHandle(e.target.value);
  };
  
  //function to retrieve the document id from Firestore.
  const getProfileDocId = async (cleanHandle: string, category: 'twitter' | 'linkedin'): Promise<string | null> => {
    const q = query(
      collection(db, 'plugins_data'),
      where('username', '==', cleanHandle.toLowerCase()),
      where('connected_accounts', 'array-contains', category)
    );

    const q2 = query(
      collection(db, 'plugins_data'),
      where('username', '==', cleanHandle.toLowerCase()),
      where('category', '==', category)
    );

    const [querySnapshot1, querySnapshot2] = await Promise.all([
      getDocs(q),
      getDocs(q2)
    ]);

    if (!querySnapshot1.empty || !querySnapshot2.empty) {
      const doc = querySnapshot1.empty ? querySnapshot2.docs[0] : querySnapshot1.docs[0];
      return doc.id;
    }
    return null;
  };

  //helper functions to extract handles from specific platforms
  const extractTwitterHandle = (input: string): string | null => {
    const trimmedInput = input.trim();
    const twitterMatch = trimmedInput.match(/x\.com\/(?:#!\/)?@?([^/?]+)/i);
    if (twitterMatch && twitterMatch[1]) {
      return twitterMatch[1];
    }
    return null;
  };

  const extractLinkedinHandle = (input: string): string | null => {
    const trimmedInput = input.trim();
    const linkedinMatch = trimmedInput.match(/linkedin\.com\/in\/([^/?]+)/i);
    if (linkedinMatch && linkedinMatch[1]) {
      return linkedinMatch[1];
    }
    return null;
  };

  //helper function to extract a handle from a URL or raw handle input.
  const extractHandle = (input: string): string => {
    // Try platform-specific extractors first
    const twitterHandle = extractTwitterHandle(input);
    if (twitterHandle) return twitterHandle;
    
    const linkedinHandle = extractLinkedinHandle(input);
    if (linkedinHandle) return linkedinHandle;
    
    // If not a URL, remove leading '@' if present
    const trimmedInput = input.trim();
    return trimmedInput.startsWith('@') ? trimmedInput.substring(1) : trimmedInput;
  };

  // Helper functions to determine input type
  const isTwitterInput = (input: string): boolean => {
    return /x\.com\//i.test(input.trim());
  };

  const isLinkedinInput = (input: string): boolean => {
    return /linkedin\.com\//i.test(input.trim());
  };

  const checkExistingProfile = async (cleanHandle: string, category: 'twitter' | 'linkedin'): Promise<string | null> => {
    const q = query(
      collection(db, 'plugins_data'),
      where('username', '==', cleanHandle.toLowerCase()),
      where('connected_accounts', 'array-contains', category)
    );

    const q2 = query(
      collection(db, 'plugins_data'),
      where('username', '==', cleanHandle.toLowerCase()),
      where('category', '==', category)
    );

    const [querySnapshot1, querySnapshot2] = await Promise.all([
      getDocs(q),
      getDocs(q2)
    ]);

    if (!querySnapshot1.empty || !querySnapshot2.empty) {
      const doc = querySnapshot1.empty ? querySnapshot2.docs[0] : querySnapshot1.docs[0];
      return doc.id;
    }
    return null;
  };

  // handleCreatePersona function using redirectToChat in all cases.
  const handleCreatePersona = async () => {
    setIsCreating(true);
    
    try {
      const trimmedInput = handle.trim();
      const cleanHandle = extractHandle(trimmedInput);
      if (!cleanHandle) {
        toast.error('Invalid handle or URL');
        return;
      }
      
      let twitterResult = false;
      let linkedinResult = false;
      let existingId: string | null = null;
      
      // If input is specifically a Twitter URL
      if (isTwitterInput(trimmedInput)) {
        existingId = await checkExistingProfile(cleanHandle, 'twitter');
        if (existingId) {
          twitterResult = true;
          toast.success('Profile already exists, redirecting...');
          redirectToChat(existingId);
          return;
        } else {
          twitterResult = await fetchTwitterProfile(cleanHandle);
          if (twitterResult) {
            existingId = await checkExistingProfile(cleanHandle, 'twitter');
            if (existingId) {
              redirectToChat(existingId);
              return;
            }
          }
        }
      } 
      // If input is specifically a LinkedIn URL
      else if (isLinkedinInput(trimmedInput)) {
        existingId = await checkExistingProfile(cleanHandle, 'linkedin');
        if (existingId) {
          linkedinResult = true;
          toast.success('Profile already exists, redirecting...');
          redirectToChat(existingId);
          return;
        } else {
          linkedinResult = await fetchLinkedinProfile(cleanHandle);
          if (linkedinResult) {
            existingId = await checkExistingProfile(cleanHandle, 'linkedin');
            if (existingId) {
              redirectToChat(existingId);
              return;
            }
          }
        }
      } 
      // If input is a generic handle, try both platforms
      else {
        // Try Twitter first
        twitterResult = await fetchTwitterProfile(cleanHandle);

        // Then try LinkedIn
        linkedinResult = await fetchLinkedinProfile(cleanHandle);

        // Handle the case where both platforms have results
        if (twitterResult && linkedinResult) {
          setPendingCleanHandle(cleanHandle);
          setShowPlatformModal(true);
          return;
        }
        if (twitterResult) {
          const docId = await getProfileDocId(cleanHandle, 'twitter');
          if (docId) {
            redirectToChat(docId);
          }
          return;
        }
        if (linkedinResult) {
          const docId = await getProfileDocId(cleanHandle, 'linkedin');
          if (docId) {
            redirectToChat(docId);
          }
          return;
        }
      }
      
      // If we got here, no profiles were found or created
      if (!twitterResult && !linkedinResult) {
        toast.error('No profiles found for the given handle.');
      }
    } catch (error) {
      console.error('Error in handleCreatePersona:', error);
      toast.error('Failed to create or find the persona.');
    } finally {
      setIsCreating(false);
    }
  };

  //handler for modal selection.
  const handlePlatformSelect = async (platform: 'twitter' | 'linkedin') => {
    if (pendingCleanHandle) {
      const existingId = await checkExistingProfile(pendingCleanHandle, platform);
      if (existingId) {
        toast.success('Profile already exists, redirecting...');
        redirectToChat(existingId);
      } else {
        toast.error('No profiles found for the given handle.');
      }
    }
    setShowPlatformModal(false);
    setPendingCleanHandle(null);
  };

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
        orderBy('sub_count', 'desc')
      );

      if (!isInitial && lastDoc) {
        q = query(q, startAfter(lastDoc), limit(BOTS_PER_PAGE));
      } else {
        q = query(q, limit(BOTS_PER_PAGE));
      }

      const querySnapshot = await getDocs(q);

      // Single Map for all bots, keyed by lowercase username and category
      const allBotsMap = new Map();

      querySnapshot.docs.forEach(doc => {
        const bot = { id: doc.id, ...doc.data() } as Chatbot;
        const normalizedUsername = bot.username?.toLowerCase().trim();
        const category = bot.category;

        if (!normalizedUsername || !bot.name) return;

        const key = `${normalizedUsername}-${category}`;
        const existingBot = allBotsMap.get(key);

        // Only update if new bot has higher sub_count
        if (!existingBot || ((bot.sub_count || 0) > (existingBot.sub_count || 0))) {
          allBotsMap.set(key, bot);
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
            const category = bot.category;
            if (username) {
              const key = `${username}-${category}`;
              masterMap.set(key, bot);
            }
          });

          // Then add new bots, only updating if sub_count is higher
          uniqueBots.forEach(bot => {
            const username = bot.username?.toLowerCase().trim();
            const category = bot.category;
            if (username) {
              const key = `${username}-${category}`;
              const existingBot = masterMap.get(key);
              if (!existingBot || ((bot.sub_count || 0) > (existingBot.sub_count || 0))) {
                masterMap.set(key, bot);
              }
            }
          });

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

  const redirectToChat = (id: string) => {
    router.push(`/chat?id=${encodeURIComponent(id)}`);
  };

  const fetchTwitterProfile = async (twitterHandle: string) => {
    if (!twitterHandle) return false;
    const cleanHandle = twitterHandle.replace('@', '');
    setIsCreating(true);
    try {
      if (await checkExistingProfile(cleanHandle, 'twitter')) return true;
      const profileResponse = await fetch(`https://${process.env.NEXT_PUBLIC_RAPIDAPI_HOST}/screenname.php?screenname=${cleanHandle}`, {
        headers: {
          'x-rapidapi-key': process.env.NEXT_PUBLIC_RAPIDAPI_KEY!,
          'x-rapidapi-host': process.env.NEXT_PUBLIC_RAPIDAPI_HOST!,
        },
      });
      if (!profileResponse.ok) return false;
      const profileData: TwitterProfile = await profileResponse.json();
      if (!profileData || !profileData.name) return false;
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

      const persona_id = ulid();
      const docData = {
        'id': persona_id,
        'name': profileData.name,
        'username': cleanHandle.toLowerCase(),
        'description': profileData.desc || 'This is my personal AI clone',
        'image': formattedAvatarUrl,
        'uid': auth.currentUser?.uid || null,
        'author': profileData.name,
        'email': auth.currentUser?.email || '',
        'approved': true,
        'deleted': false,
        'status': 'approved',
        'category': 'personality-emulation',
        'capabilities': ['persona'],
        'connected_accounts': ['twitter'],
        'created_at': new Date().toISOString(),
        'private': false,
        'persona_prompt': fullChatPrompt,
        'avatar': formattedAvatarUrl,
        'twitter': {
          'username': cleanHandle.toLowerCase(),
          'avatar': formattedAvatarUrl,
          'connected_at': new Date().toISOString(),
        }
      };

      const docRef = await setDoc(doc(db, 'plugins_data', persona_id), docData);

      // Store the created persona ID in localStorage only if user is not authenticated
      if (!auth.currentUser) {
        const createdPersonas = JSON.parse(localStorage.getItem('createdPersonas') || '[]');
        createdPersonas.push(persona_id);
        localStorage.setItem('createdPersonas', JSON.stringify(createdPersonas));
      }

      toast.success('Profile saved successfully!');

      // router.push(`/chat?id=${persona_id}`);
      return true;

    } catch (error) {
      console.error('Error fetching Twitter profile:', error);
      return false;
    } finally {
      setIsCreating(false);
    }
  };

  const fetchLinkedinProfile = async (linkedinHandle: string) => {
    if (!linkedinHandle) return false;
    const cleanHandle = linkedinHandle.replace('@', '');
    setIsCreating(true);
    try {
      if (await checkExistingProfile(cleanHandle, 'linkedin')) return true;
      const encodedHandle = encodeURIComponent(cleanHandle);
      const profileResponse = await fetch(`https://${process.env.NEXT_PUBLIC_LINKEDIN_API_HOST}/profile-data-connection-count-posts?username=${encodedHandle}`, {
        headers: {
          'x-rapidapi-key': process.env.NEXT_PUBLIC_LINKEDIN_API_KEY!,
          'x-rapidapi-host': process.env.NEXT_PUBLIC_LINKEDIN_API_HOST!,
        },
      });
      if (!profileResponse.ok) return false;
      const profileData: LinkedinProfile = await profileResponse.json();
      if (!profileData || !profileData?.data?.firstName) return false;
      const formattedAvatarUrl = profileData?.data?.profilePicture || 'https://storage.googleapis.com/omi_plugins/dummy_linkedin_image.png';
      const fullName = `${profileData?.data?.firstName || ''} ${profileData?.data?.lastName || ''}`.trim();
      const headline = profileData?.data?.headline || 'No headline available';
      const summary = profileData?.data?.summary || 'No summary available';
      const positions = Array.isArray(profileData?.data?.position)
        ? profileData.data.position.map(pos => {
            const title = pos?.title || 'Unknown Title';
            const company = pos?.companyName || 'Unknown Company';
            const startYear = pos?.start?.year || 'N/A';
            const endYear = pos?.end?.year || 'Present';
            return `${title} at ${company} (${startYear} - ${endYear})`;
          }).join(', ')
        : 'No positions available';
      const skills = Array.isArray(profileData?.data?.skills)
        ? profileData.data.skills.map(skill => skill?.name || '').filter(Boolean).join(', ')
        : 'No skills available';
      const recentPosts = Array.isArray(profileData?.posts)
        ? profileData.posts.map(post => post?.text || '').filter(Boolean).join('\n')
        : 'No recent posts available';
      const enhancedDesc = `${summary}\n\nPositions: ${positions}\n\nSkills: ${skills}\n\nRecent Posts:\n${recentPosts}`;
      const extraPromptRules = process.env.NEXT_PUBLIC_EXTRA_PROMPT_RULES ?? "";
      const fullChatPrompt = `You are ${fullName}, an AI persona. Here is some information about you:
      
Name: ${fullName}
Headline: ${headline}
Summary: ${summary}
Positions: ${positions}
Skills: ${skills}

Style:
- Interactive highly opinionated messages and questions.
- Reference your experiences and skills naturally.

Rules:
- Never mention being AI
- No ** or formal language
- 2-3 sentences for response. Never more than 20 words.
- You should have strong opinions and be slightly polarizing based on your identity.
- You must make the conversation flow. You excel at coherent conversations.
${extraPromptRules}

Recent activity on Linkedin:\n"${enhancedDesc}" which you can use for your personality. Responses should help the conversation go deeper. You have strong opinions, slightly controversial.`;
      try {
        const persona_id = ulid();
        const docData = {
          'id': persona_id,
          'name': fullName,
          'username': cleanHandle.toLowerCase().replace('@', ''),
          'description': enhancedDesc || 'This is my personal AI clone',
          'image': formattedAvatarUrl,
          'uid': auth.currentUser?.uid || null,
          'author': fullName,
          'email': auth.currentUser?.email || '',
          'approved': true,
          'deleted': false,
          'status': 'approved',
          'category': 'personality-emulation',
          'capabilities': ['persona'],
          'connected_accounts': ['linkedin'],
          'connected_at': new Date().toISOString(),
          'private': false,
          'persona_prompt': fullChatPrompt,
          'avatar': formattedAvatarUrl,
          'linkedin': {
            'username': cleanHandle.toLowerCase(),
            'avatar': formattedAvatarUrl,
            'connected_at': new Date().toISOString(),
          }
        };

        const docRef = await setDoc(doc(db, 'plugins_data', persona_id), docData);

        // Store the created persona ID in localStorage only if user is not authenticated
        if (!auth.currentUser) {
          const createdPersonas = JSON.parse(localStorage.getItem('createdPersonas') || '[]');
          createdPersonas.push(persona_id);
          localStorage.setItem('createdPersonas', JSON.stringify(createdPersonas));
        }

        toast.success('Profile saved successfully!');
        return true;
      } catch (firebaseError) {
        console.error('Firebase error:', firebaseError);
        toast.error('Failed to save profile');
        return false;
      }
    } catch (error) {
      console.error('Error fetching LinkedIn profile:', error);
      return false;
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-white">
      <PreorderBanner botName="your favorite personal" />
      <Header />
      <div className="flex flex-col items-center px-4 py-8 md:py-16">
        <InputArea
          handle={handle}
          handleInputChange={handleInputChange}
          handleCreatePersona={handleCreatePersona}
          isCreating={isCreating}
        />
        {!loading && (
          <ChatbotList
            chatbots={filteredChatbots}
            handleChatbotClick={handleChatbotClick}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            ref={ref}
            hasMore={hasMore}
          />
        )}
      </div>
      <Footer />
      {/* Render the modal */}
      <PlatformSelectionModal
        isOpen={showPlatformModal}
        onClose={() => {
          setShowPlatformModal(false);
          setPendingCleanHandle(null);
        }}
        platforms={availablePlatforms}
        onSelect={handlePlatformSelect}
        mode={platformSelectionMode}
      />
    </div>
  );
}

