import { useLocalSearchParams, Redirect } from 'expo-router';
import { useAuthStore } from '@/state/authStore';
import ConversationDetailScreen from '@/screens/ConversationDetailScreen';

export default function ConversationDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const uid = useAuthStore((s) => s.uid);

  if (!uid) {
    return <Redirect href="/onboarding" />;
  }

  return <ConversationDetailScreen id={id ?? ''} />;
}
