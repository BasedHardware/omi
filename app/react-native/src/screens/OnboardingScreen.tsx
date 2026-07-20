import React from 'react';
import {
  View,
  Text,
  ImageBackground,
  TouchableOpacity,
  ActivityIndicator,
  Linking,
  StyleSheet,
  StatusBar,
  Platform,
} from 'react-native';
import { Redirect } from 'expo-router';
import { FontAwesome } from '@expo/vector-icons';
import { useAuthStore } from '@/state/authStore';

const BG = require('../../assets/images/onboarding-bg.webp');

export default function OnboardingScreen() {
  const { uid, loading, error, loginWithGoogle, loginWithApple } = useAuthStore();

  if (uid) {
    return <Redirect href="/(tabs)/home" />;
  }

  return (
    <View style={styles.flex}>
      <ImageBackground source={BG} style={styles.flex} resizeMode="cover">
        <View style={[styles.flex, { paddingTop: Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 0 }]}>
          <View style={styles.spacer} />

          <View style={[styles.card, { paddingBottom: 16 }]}>
            {loading && (
              <ActivityIndicator
                style={{ marginBottom: 16 }}
                color="#fff"
                size="small"
              />
            )}

            <Text style={styles.title}>Speak. Transcribe. Summarize.</Text>

            <View style={styles.buttons}>
              <TouchableOpacity
                style={styles.button}
                onPress={loginWithApple}
                disabled={loading}
                accessibilityRole="button"
                accessibilityLabel="Sign in with Apple"
              >
                <FontAwesome name="apple" size={22} color="#000" />
                <Text style={styles.buttonText}>Sign in with Apple</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.button}
                onPress={loginWithGoogle}
                disabled={loading}
                accessibilityRole="button"
                accessibilityLabel="Sign in with Google"
              >
                <FontAwesome name="google" size={20} color="#000" />
                <Text style={styles.buttonText}>Sign in with Google</Text>
              </TouchableOpacity>
            </View>

            {error && <Text style={styles.error}>{error}</Text>}

            <Text style={styles.legal}>
              By continuing you agree to our{' '}
              <Text style={styles.link} onPress={() => Linking.openURL('https://www.omi.me/pages/privacy')}>
                Privacy Policy
              </Text>{' '}
              &{' '}
              <Text style={styles.link} onPress={() => Linking.openURL('https://www.omi.me/pages/terms-of-service')}>
                Terms of Service
              </Text>
              .
            </Text>
          </View>
        </View>
      </ImageBackground>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  spacer: { flex: 1 },
  card: {
    backgroundColor: '#000',
    borderTopLeftRadius: 40,
    borderTopRightRadius: 40,
    paddingTop: 28,
    paddingHorizontal: 32,
    paddingBottom: 24,
  },
  title: {
    color: '#fff',
    fontSize: 32,
    fontWeight: '700',
    textAlign: 'center',
    lineHeight: 38,
    marginBottom: 28,
  },
  buttons: {
    gap: 16,
  },
  button: {
    height: 56,
    borderRadius: 28,
    backgroundColor: '#fff',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  buttonText: {
    color: '#000',
    fontSize: 18,
    fontWeight: '600',
  },
  error: {
    color: '#ff6b6b',
    fontSize: 13,
    textAlign: 'center',
    marginTop: 14,
  },
  legal: {
    color: 'rgba(255,255,255,0.6)',
    fontSize: 11,
    textAlign: 'center',
    marginTop: 20,
  },
  link: {
    textDecorationLine: 'underline',
    color: 'rgba(255,255,255,0.6)',
  },
});
