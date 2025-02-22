import { Metadata, ResolvingMetadata } from 'next';
import { collection, query, where, getDocs } from 'firebase/firestore';
import { db } from '@/lib/firebase';
import { TwitterProfile } from '@/types/twitter';

const formatTwitterAvatarUrl = (url: string): string => {
  if (!url) return '/omi-avatar.svg';
  let formattedUrl = url.replace('http://', 'https://');
  formattedUrl = formattedUrl.replace('_normal', '');
  if (formattedUrl.includes('pbs.twimg.com')) {
    formattedUrl = formattedUrl.replace('/profile_images/', '/profile_images/');
  }
  return formattedUrl;
};

type Props = {
  params: Promise<{ username: string }>
  children: React.ReactNode
}

export async function generateMetadata(
  { params }: Props,
  parent: ResolvingMetadata
): Promise<Metadata> {
  const { username } = await params;
  
  try {
    // First try Firestore
    const q = query(
      collection(db, 'plugins_data'),
      where('username', '==', username.toLowerCase())
    );
    const querySnapshot = await getDocs(q);

    if (!querySnapshot.empty) {
      const botDoc = querySnapshot.docs[0];
      const botData = botDoc.data();
      
      return {
        metadataBase: new URL('https://personas.omi.me'),
        title: `${botData.name} | Ask me anything`,
        description: botData.profile || 'Ask me anything on Omi',
        openGraph: {
          title: `${botData.name} | Ask me anything`,
          description: botData.profile || 'Ask me anything on Omi',
          type: 'website',
          images: [
            {
              url: botData.image || '/omidevice.webp',
              width: 400,
              height: 400,
              alt: `${botData.name}'s profile picture`,
            }
          ],
        },
        twitter: {
          card: 'summary',
          title: `${botData.name} | Ask me anything`,
          description: botData.profile || 'Ask me anything on Omi',
          images: [botData.image || '/omidevice.webp'],
          creator: '@omiai',
          site: '@omiai'
        }
      };
    }

    // If not in Firestore, try Twitter API
    const profileResponse = await fetch(`https://${process.env.NEXT_PUBLIC_RAPIDAPI_HOST}/screenname.php?screenname=${username}`, {
      headers: {
        'x-rapidapi-key': process.env.NEXT_PUBLIC_RAPIDAPI_KEY!,
        'x-rapidapi-host': process.env.NEXT_PUBLIC_RAPIDAPI_HOST!,
      },
    });

    const profileData: TwitterProfile = await profileResponse.json();
    
    if (profileData && profileData.name) {
      const formattedAvatarUrl = formatTwitterAvatarUrl(profileData.avatar);
      
      return {
        metadataBase: new URL('https://personas.omi.me'),
        title: `${profileData.name} | Ask me anything`,
        description: profileData.desc || 'Ask me anything on Omi',
        openGraph: {
          title: `${profileData.name} | Ask me anything`,
          description: profileData.desc || 'Ask me anything on Omi',
          type: 'website',
          images: [
            {
              url: formattedAvatarUrl,
              width: 400,
              height: 400,
              alt: `${profileData.name}'s profile picture`,
            }
          ],
        },
        twitter: {
          card: 'summary',
          title: `${profileData.name} | Ask me anything`,
          description: profileData.desc || 'Ask me anything on Omi',
          images: [formattedAvatarUrl],
          creator: '@omiai',
          site: '@omiai'
        }
      };
    }
  } catch (error) {
    console.error('Error fetching metadata:', error);
  }

  // Default metadata for not found/private/error cases
  return {
    metadataBase: new URL('https://personas.omi.me'),
    title: 'Ask me anything on Omi',
    description: 'Ask me anything on Omi',
    openGraph: {
      title: 'Ask me anything on Omi',
      description: 'Ask me anything on Omi',
      type: 'website',
      images: [
        {
          url: '/omidevice.webp',
          width: 400,
          height: 400,
          alt: 'Omi Profile Picture',
        }
      ],
    },
    twitter: {
      card: 'summary',
      title: 'Ask me anything on Omi',
      description: 'Ask me anything on Omi',
      images: ['/omidevice.webp'],
      creator: '@omiai',
      site: '@omiai'
    }
  };
}

export default function Layout({ children }: Props) {
  return children;
} 