import { Redirect } from 'expo-router';
import { useAuthStore } from '@/state/authStore';

export default function Index() {
  const uid = useAuthStore((s) => s.uid);
  const loading = useAuthStore((s) => s.loading);
  if (loading) return null;
  return <Redirect href={uid ? '/(tabs)/home' : '/onboarding'} />;
}
