import React from 'react';
import { Tabs, Redirect } from 'expo-router';
import { useAuthStore } from '@/state/authStore';

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
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: '#000000',
          borderTopColor: '#2C2C2E',
          borderTopWidth: 0.5,
          height: 60,
          paddingTop: 6,
        },
        tabBarActiveTintColor: '#FFFFFF',
        tabBarInactiveTintColor: '#8E8E93',
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
      }}
    >
      <Tabs.Screen name="home" options={{ title: 'Home' }} />
      <Tabs.Screen name="conversations" options={{ title: 'Conversations' }} />
      <Tabs.Screen name="goals" options={{ title: 'Goals' }} />
      <Tabs.Screen name="apps" options={{ title: 'Apps' }} />
      <Tabs.Screen name="settings" options={{ href: null, title: 'Settings' }} />
    </Tabs>
  );
}
