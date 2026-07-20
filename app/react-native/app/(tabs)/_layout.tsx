import React from 'react';
import { Tabs, Redirect } from 'expo-router';
import { useAuthStore } from '@/state/authStore';
import HomeScreen from '@/screens/HomeScreen';
import ConversationsScreen from '@/screens/ConversationsScreen';
import MemoriesScreen from '@/screens/MemoriesScreen';
import AppsScreen from '@/screens/AppsScreen';
import SettingsScreen from '@/screens/SettingsScreen';

export default function TabsLayout() {
  const uid = useAuthStore((s) => s.uid);

  if (!uid) {
    return <Redirect href="/onboarding" />;
  }

  return (
    <Tabs screenOptions={{ headerShown: false }}>
      <Tabs.Screen name="home" options={{ title: 'Home' }} />
      <Tabs.Screen name="conversations" options={{ title: 'Conversations' }} />
      <Tabs.Screen name="memories" options={{ title: 'Memories' }} />
      <Tabs.Screen name="apps" options={{ title: 'Apps' }} />
      <Tabs.Screen name="settings" options={{ title: 'Settings' }} />
    </Tabs>
  );
}
