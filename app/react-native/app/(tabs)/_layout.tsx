import React from 'react';
import { Tabs, Redirect } from 'expo-router';
import { useAuthStore } from '@/state/authStore';
import HomeScreen from '@/screens/HomeScreen';
import ConversationsScreen from '@/screens/ConversationsScreen';
import GoalsScreen from '@/screens/GoalsScreen';
import AppsScreen from '@/screens/AppsScreen';
import SettingsScreen from '@/screens/SettingsScreen';

export default function TabsLayout() {
  const uid = useAuthStore((s) => s.uid);

  // Kept strict. An earlier version skipped this redirect behind an env flag to
  // reach the local brain without signing in; that made the tabs appear at launch
  // and left the app with no obvious way back to sign-in. The "continue without
  // account" button on the sign-in screen sets a real local session instead, so
  // this gate still means what it says.
  if (!uid) {
    return <Redirect href="/onboarding" />;
  }

  return (
    <Tabs screenOptions={{ headerShown: false }}>
      <Tabs.Screen name="home" options={{ title: 'Home' }} />
      <Tabs.Screen name="conversations" options={{ title: 'Conversations' }} />
      <Tabs.Screen name="goals" options={{ title: 'Goals' }} />
      <Tabs.Screen name="apps" options={{ title: 'Apps' }} />
      <Tabs.Screen name="settings" options={{ href: null, title: 'Settings' }} />
    </Tabs>
  );
}
