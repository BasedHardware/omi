'use client';

// ------------------------------------------------------------------------------------
// TEMPORARY: Force a fixed UID for end‑to‑end testing in prod/staging environments.
//            Comment out or delete the following line (and its usages) once testing is
//            finished and real Firebase anonymous/authenticated UIDs should be used.
// export const TEST_UID = "kiTPO8XwMlOpFpb4x1diyMg213j2"; // <-- commented after tests
// ------------------------------------------------------------------------------------

import { SetStateAction, useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { db } from '@/lib/firebase';
import { collection, addDoc, query, where, getDocs, orderBy, startAfter, limit, doc, setDoc, getDoc, or } from 'firebase/firestore';
import { toast } from 'sonner';
import { Mixpanel } from '@/lib/mixpanel';
import { useInView } from 'react-intersection-observer';
import { ulid } from 'ulid';
import { auth, googleProvider } from '@/lib/firebase';
import { Header } from '@/components/Header';
import { InputArea } from '@/components/InputArea';
import { ChatbotList } from '@/components/ChatbotList';
import { Footer } from '@/components/Footer';
import { LoginDialog } from '@/components/LoginDialog';
import { Chatbot, TwitterProfile, LinkedinProfile } from '@/types/profiles';
import { PreorderBanner } from '@/components/shared/PreorderBanner';
import { signInAnonymously, onAuthStateChanged, User, signInWithPopup } from 'firebase/auth';

// Helper function to detect mobile devices (basic check)
const isMobileDevice = (): boolean => {
  if (typeof window === 'undefined') return false;
  // Basic check using userAgent - consider a library like 'react-device-detect' for more robustness
  return /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
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
  const [currentUserUid, setCurrentUserUid] = useState<string | null>(null);
  const [authInitialized, setAuthInitialized] = useState<boolean>(false);
  const [isIntegrating, setIsIntegrating] = useState(false);
  const [showLoginDialog, setShowLoginDialog] = useState(false);
  const [pendingProvider, setPendingProvider] = useState<string | null>(null);

  // ----------------------------------------------------------------------------------
  // Helper: open ChatGPT workspace - NOW WITH MOBILE HANDLING
  // Comment or delete after tests together with TEST_UID declarations.
  const openChatGPTWithUid = (uid: string) => {
    const isMobile = isMobileDevice();
    const baseChatGPTUrl = 'https://chatgpt.com/g/g-67e2772d0af081919a5baddf4a12aacf-omigpt';

    console.log(`[openChatGPTWithUid] Detected mobile: ${isMobile}`);

    if (isMobile) {
      // Mobile flow: Copy UID, show toast, redirect after delay
      navigator.clipboard.writeText(uid)
        .then(() => {
          console.log('[openChatGPTWithUid] UID copied to clipboard for mobile.');
          toast.success('UID copied! Paste it into ChatGPT.', {
            duration: 3000, // Show toast for 3 seconds
          });
          // Redirect after toast duration
          setTimeout(() => {
            console.log(`[openChatGPTWithUid] Redirecting mobile to base URL: ${baseChatGPTUrl}`);
            window.location.href = baseChatGPTUrl;
          }, 3000);
        })
        .catch(err => {
          console.error('[openChatGPTWithUid] Failed to copy UID to clipboard:', err);
          // Show UID in the error toast for manual copying
          toast.error(`Redirecting to integration partner`, {
             duration: 5000, // Give a bit more time to see/copy
          });
          // Still redirect after a delay, allowing time for manual copy
          setTimeout(() => {
            console.log(`[openChatGPTWithUid] Redirecting mobile (after copy fail) to base URL: ${baseChatGPTUrl}`);
            window.location.href = baseChatGPTUrl;
          }, 5000); // Increased delay
        });
    } else {
      const redirectUrl = `${baseChatGPTUrl}?prompt=uid=${encodeURIComponent(uid)}`;
      console.log(`[openChatGPTWithUid] Redirecting desktop to: ${redirectUrl}`);
      window.location.href = redirectUrl;
    }
  };

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user: User | null) => {
      if (user) {
        setCurrentUserUid(user.uid);
      } else {
        console.log('No authenticated user found.');
        setCurrentUserUid(null);
      }
      setAuthInitialized(true);
    });

    return () => unsubscribe();
  }, []);

  const getUid = async (): Promise<string | null> => {
    if (!authInitialized) {
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    if (currentUserUid) {
      return currentUserUid;
    }

    if (auth.currentUser) {
      setCurrentUserUid(auth.currentUser.uid);
      return auth.currentUser.uid;
    }

    if (pendingProvider || handle) {
      setShowLoginDialog(true);
      return null;
    }

    try {
      const result = await signInAnonymously(auth);
      const newUid = result.user.uid;
      setCurrentUserUid(newUid);
      return newUid;
    } catch (err) {
      console.error('Anonymous sign-in failed:', err);
      toast.error('Failed to initialize user session.');
      return null;
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const profileParam = params.get('profile');
    
    if (profileParam) {
      const cleanHandle = extractHandle(profileParam);
      setHandle(cleanHandle);
      handleCreatePersona(cleanHandle);
    }
  }, []);

  const handleInputChange = (e: { target: { value: SetStateAction<string>; }; }) => {
    setHandle(e.target.value);
  };
  
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

  // Modified handleCreatePersona to accept a new optional handle parameter
  const handleCreatePersona = async (inputHandle?: string) => {
    if (isCreating) return;
    
    const handleToUse = (inputHandle || handle || '').toString();
    if (!handleToUse || handleToUse.trim() === '') {
      toast.error('Please enter a handle');
      return;
    }

    setIsCreating(true);

    Mixpanel.track('Create Persona Clicked', {
      input: handleToUse,
      timestamp: new Date().toISOString()
    });

    try {
      const cleanHandle = extractHandle(handleToUse);
      let twitterResult = false;
      let linkedinResult = false;
      let existingId: string | null = null;

      // Check if it's a specific platform URL
      if (isTwitterInput(handleToUse)) {
        existingId = await checkExistingProfile(cleanHandle, 'twitter');
        if (existingId) {
          // Existing persona found – open ChatGPT directly
          const uid = await getUid();
          if (uid) openChatGPTWithUid(uid);
          else toast.error('Could not get user ID to redirect.');
          return;
        }
        twitterResult = await fetchTwitterProfile(cleanHandle);
        if (twitterResult) {
          return;
        }
      } else if (isLinkedinInput(handleToUse)) {
        existingId = await checkExistingProfile(cleanHandle, 'linkedin');
        if (existingId) {
          // Existing persona found – open ChatGPT directly
          const uid = await getUid();
          if (uid) openChatGPTWithUid(uid);
          else toast.error('Could not get user ID to redirect.');
          return;
        }
        linkedinResult = await fetchLinkedinProfile(cleanHandle);
        if (linkedinResult) {
          return;
        }
      } else {
        // Try Twitter first
        twitterResult = await fetchTwitterProfile(cleanHandle);
        if (twitterResult) {
          return;
        }

        // Then try LinkedIn
        linkedinResult = await fetchLinkedinProfile(cleanHandle);
        if (linkedinResult) {
          return;
        }
      }
      
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
        const uid = await getUid();
        if (uid) openChatGPTWithUid(uid);
        else toast.error('Could not get user ID to redirect.');
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

      const allBotsMap = new Map();

      querySnapshot.docs.forEach(doc => {
        const bot = { id: doc.id, ...doc.data() } as Chatbot;
        const normalizedUsername = bot.username?.toLowerCase().trim();
        const category = bot.category;

        if (!normalizedUsername || !bot.name) return;

        const key = `${normalizedUsername}-${category}`;
        const existingBot = allBotsMap.get(key);

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

          prev.forEach(bot => {
            const username = bot.username?.toLowerCase().trim();
            const category = bot.category;
            if (username) {
              const key = `${username}-${category}`;
              masterMap.set(key, bot);
            }
          });

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
      const profileExists = await checkExistingProfile(cleanHandle, 'twitter');
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
      const uid = await getUid();
      if (!uid) {
        // getUid already shows a toast on failure
        return false; // Cannot proceed without UID
      }

      const docData = {
        'id': persona_id,
        'name': profileData.name,
        'username': cleanHandle.toLowerCase(),
        'description': profileData.desc || 'This is my personal AI clone',
        'image': formattedAvatarUrl,
        'uid': uid,
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

      if (!profileExists) {
        await setDoc(doc(db, 'plugins_data', persona_id), docData);
      }

      // Enable default plugins in Redis
      try {
        const enableRes = await fetch('/api/enable-plugins', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uid: uid }) 
        });
        if (!enableRes.ok) {
          console.error('Failed to enable plugins via API:', await enableRes.text());
        }
      } catch (apiErr) {
        console.error('Error calling /api/enable-plugins:', apiErr);
      }

      const memories = [profileData.desc || '', ...recentTweets];
      storeFactsAndRedirect(uid, memories.filter(Boolean)); 

      toast.success('Profile saved successfully!');

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
      const profileExists = await checkExistingProfile(cleanHandle, 'linkedin');
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
        const uid = await getUid();
        if (!uid) {
          return false; 
        }

        const persona_id = ulid();
        const docData = {
          'id': persona_id,
          'name': fullName,
          'username': cleanHandle.toLowerCase().replace('@', ''),
          'description': enhancedDesc || 'This is my personal AI clone',
          'image': formattedAvatarUrl,
          'uid': uid,
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

        if (!profileExists) {
          await setDoc(doc(db, 'plugins_data', persona_id), docData);
        }

        try {
          const enableRes = await fetch('/api/enable-plugins', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ uid: uid }) 
          });
          if (!enableRes.ok) {
            console.log('Failed to enable plugins via API:', await enableRes.text());
          }
        } catch (apiErr) {
          console.log('Error calling /api/enable-plugins:', apiErr);
        }

        const memories = [summary, recentPosts].filter(Boolean);
        storeFactsAndRedirect(uid, memories); 

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

  const storeFactsAndRedirect = async (uid: string, memories: string[]) => {
    if (!uid || memories.length === 0) {
      console.warn('[storeFactsAndRedirect] No UID or no memories provided, redirecting anyway.');
      openChatGPTWithUid(uid || 'NO_UID_PROVIDED'); 
      return;
    }
    
    try {
      fetch('/api/store-facts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ uid, memories }),
      }).then(response => {
        if (!response.ok) {
          console.error(`[storeFactsAndRedirect] Background /api/store-facts call failed with status: ${response.status}`);
        }
      }).catch(err => {
         console.error('[storeFactsAndRedirect] Background fetch to /api/store-facts failed:', err);
      });
    } catch (err) {
      console.error('[storeFactsAndRedirect] Error initiating background fact storage:', err);
    }
    
    console.log('[storeFactsAndRedirect] Initiated background fact storage. Redirecting NOW...');
    openChatGPTWithUid(uid);
  };

  const handleAuthSuccess = (userId: string) => {
    setCurrentUserUid(userId);
    setShowLoginDialog(false);

    if (pendingProvider) {
      const savedProvider = pendingProvider;
      setPendingProvider(null);
      handleIntegrationClick(savedProvider);
    }
  };

  const handleIntegrationClick = async (provider: string) => {
    if (isIntegrating) return; 
    
    if (!auth.currentUser || auth.currentUser.isAnonymous) {
      setPendingProvider(provider);
      setShowLoginDialog(true);
      return;
    }
    
    setIsIntegrating(true);

    Mixpanel.track('Integration Clicked', {
      provider: provider,
      timestamp: new Date().toISOString()
    });
    
    const isMobile = isMobileDevice();
    let loadingToastId: string | number | undefined = undefined;

    if (isMobile) {
      loadingToastId = toast.loading('Connecting...');
    }

    let uid: string | null = null;

    try {
      if (auth.currentUser) {
        uid = auth.currentUser.uid;
      } else {
        uid = await getUid(); 
      }
      if (!uid) {
        if (loadingToastId) toast.dismiss(loadingToastId);
        toast.error('Could not get user ID. Please try again.');
        setIsIntegrating(false); 
        return;
      }
      
      fetch('/api/enable-plugins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid: uid })
      }).then(async response => {
          if (!response.ok) {
            console.error(`[handleIntegrationClick] Background /api/enable-plugins call failed for provider ${provider}:`, await response.text());
          } else {
            console.log(`[handleIntegrationClick] Background /api/enable-plugins call successful for UID: ${uid}`);
          }
        }).catch(apiErr => {
          console.error(`[handleIntegrationClick] Background /api/enable-plugins fetch failed for provider ${provider}:`, apiErr);
        });
        
      const redirectUrl = `https://veyrax.com/user/omi?omi_user_id=${encodeURIComponent(uid)}&provider_tag=${encodeURIComponent(provider)}`;

      if (isMobile) {
        navigator.clipboard.writeText(uid)
          .then(() => {
            if (loadingToastId) toast.dismiss(loadingToastId);
            toast.success('UID copied! Paste it into ChatGPT. Redirecting to integration partner...', {
              duration: 3000,
            });
            setTimeout(() => {
              window.location.href = redirectUrl;
            }, 3000);
          })
          .catch(err => {
            if (loadingToastId) toast.dismiss(loadingToastId);
            toast.error(`Redirecting to an integration partner`, {
                duration: 5000, 
            });

            setTimeout(() => {
              window.location.href = redirectUrl; 
            }, 5000);
          });
      } else {
        if (loadingToastId) toast.dismiss(loadingToastId);
        window.location.href = redirectUrl;
      }

    } catch (error) {
      if (loadingToastId) toast.dismiss(loadingToastId);
      toast.error(`Failed to initiate integration for ${provider}.`);
      setIsIntegrating(false);
    } 
  };

  const addToolsUrl = currentUserUid ? `https://veyrax.com/omi/auth?omi_user_id=${encodeURIComponent(currentUserUid)}` : '#';

  return (
    <div className="min-h-screen bg-black text-white flex flex-col">
      <Header uid={currentUserUid} />
      <div className="flex flex-col items-center justify-center px-4 py-8 md:py-16 flex-grow">
        <InputArea
          handle={handle}
          handleInputChange={handleInputChange}
          handleCreatePersona={handleCreatePersona}
          handleIntegrationClick={handleIntegrationClick}
          isCreating={isCreating}
          isIntegrating={isIntegrating}
        />

        {currentUserUid && !auth.currentUser?.isAnonymous && (
          <div className="mt-4 text-center">
            <a
              href={addToolsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-base text-white hover:text-zinc-300 hover:underline"
              onClick={() => Mixpanel.track('Show All Integrations Clicked', { timestamp: new Date().toISOString() })}
            >
              Show all 100+ integrations →
            </a>
          </div>
        )}

        <div className="w-full max-w-5xl mt-12 md:mt-16 px-4">
          <div className="grid md:grid-cols-2 gap-8">
            <div className="bg-zinc-900 p-6 rounded-lg order-2 md:order-1">
              <h3 className="text-lg font-semibold mb-4 text-center text-zinc-400">ChatGPT</h3>
              <div className="space-y-3">
                <div className="flex justify-end">
                  <div className="bg-zinc-700 p-3 rounded-lg max-w-[80%] text-white">
                    What should I do today?
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="bg-zinc-700 p-3 rounded-lg max-w-[80%] text-zinc-200">
                    You could organize your tasks, check the weather forecast, brainstorm new ideas, or maybe learn a new skill online.
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-zinc-800 p-6 rounded-lg order-1 md:order-2 shadow-lg">
              <h3 className="text-lg font-semibold mb-4 text-center text-white">omiGPT</h3>
              <div className="space-y-3">
                <div className="flex justify-end">
                  <div className="bg-zinc-700 p-3 rounded-lg max-w-[80%] text-white">
                    What should I do today?
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="bg-zinc-600 p-3 rounded-lg max-w-[80%] text-white">
                    Based on your calendar, you have the 'Marketing Sync' at 2 PM. Your Notion page 'Q3 Launch Plan' needs review. How about blocking 1 hour now to finalize those presentation slides? Also, remember you starred that new cafe near the meeting spot on Maps.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
      <Footer />
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
      
      <LoginDialog 
        showLoginDialog={showLoginDialog}
        setShowLoginDialog={setShowLoginDialog}
        onAuthSuccess={handleAuthSuccess}
      />
    </div>
  );
}

