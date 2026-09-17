import React from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import ChevronLeft from 'lucide-react-native/icons/chevron-left';
import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {useReduceMotion} from '../app/useReduceMotion';
import {ChatMessageRow, ChatThinking} from '../ui/ChatTranscript';
import {OmiAvatar} from '../ui/OmiAvatar';
import {FocusPressable} from '../ui/Pressable';
import {mobileColor as color} from './mobileTokens';

/** Presentation only. The orchestrator retains requests, history, and scroll-follow state. */
export function MobileChat({
  messages,
  busy,
  error,
  loadingHistory,
  hasOlder,
  loadingOlder,
  onLoadOlder,
  onClose,
  onUsePrompt,
  prompts,
  composer,
  liveVoiceControl,
  scrollRef,
  onScroll,
  shouldAnimate,
}: {
  messages: readonly ChatMessage[];
  busy: boolean;
  error: string | null;
  loadingHistory: boolean;
  hasOlder: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => void;
  onClose: () => void;
  onUsePrompt: (prompt: string) => void;
  prompts: readonly string[];
  composer: React.ReactNode;
  liveVoiceControl?: React.ReactNode;
  scrollRef: React.RefObject<ScrollView | null>;
  onScroll: (event: NativeSyntheticEvent<NativeScrollEvent>) => void;
  shouldAnimate: (id: string) => boolean;
}) {
  const reduceMotion = useReduceMotion();
  const resting =
    messages.length === 0 && !busy && !loadingHistory && error === null;
  return (
    <SafeAreaView style={local.root}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={local.flex}>
        <View style={local.header}>
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Back to Home"
            onPress={onClose}
            style={local.back}>
            <ChevronLeft color={color.text} size={22} />
          </FocusPressable>
          <View style={local.heading}>
            <Text accessibilityRole="header" style={local.title}>
              Ask Omi
            </Text>
            <Text style={local.subtitle}>
              {busy ? 'Responding…' : 'A little room to think.'}
            </Text>
          </View>
          <OmiAvatar
            tone="ink"
            size={36}
            motion={busy ? 'breathe' : 'arrive'}
            reduceMotion={reduceMotion}
          />
        </View>
        <ScrollView
          accessibilityLabel="Chat scroll region"
          ref={scrollRef}
          onScroll={onScroll}
          scrollEventThrottle={16}
          keyboardShouldPersistTaps="handled"
          style={local.flex}
          contentContainerStyle={local.content}>
          {loadingHistory && (
            <View
              style={local.notice}
              accessibilityLabel="Loading chat history">
              <ActivityIndicator color={color.textMuted} />
              <Text style={local.copy}>Loading your conversation…</Text>
            </View>
          )}
          {hasOlder && (
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Load older messages"
              disabled={loadingOlder}
              onPress={onLoadOlder}
              style={local.older}>
              <Text style={local.copy}>
                {loadingOlder ? 'Loading older…' : 'Load older messages'}
              </Text>
            </FocusPressable>
          )}
          {resting && (
            <View style={local.resting}>
              <OmiAvatar
                tone="ink"
                size={72}
                motion="arrive"
                reduceMotion={reduceMotion}
              />
              <Text style={local.restingTitle}>Start with a thought.</Text>
              <Text style={local.restingCopy}>
                Ask about your day, untangle an idea, or find a next step.
              </Text>
              <View style={local.prompts}>
                {prompts.map(prompt => (
                  <FocusPressable
                    key={prompt}
                    accessibilityRole="button"
                    accessibilityLabel={`Try: ${prompt}`}
                    onPress={() => onUsePrompt(prompt)}
                    style={local.prompt}>
                    <Text style={local.copy}>{prompt}</Text>
                  </FocusPressable>
                ))}
              </View>
            </View>
          )}
          {messages.map(message => (
            <ChatMessageRow
              key={message.id}
              message={message}
              compact
              animate={shouldAnimate(message.id)}
              reduceMotion={reduceMotion}
            />
          ))}
          {busy && !messages.some(isStreamingAssistant) && (
            <ChatThinking reduceMotion={reduceMotion} />
          )}
          {error !== null && (
            <View style={local.error}>
              <Text accessibilityRole="alert" style={local.copy}>
                {error}
              </Text>
            </View>
          )}
        </ScrollView>
        {liveVoiceControl && <View style={local.live}>{liveVoiceControl}</View>}
        {composer}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const local = StyleSheet.create({
  root: {flex: 1, backgroundColor: color.background},
  flex: {flex: 1},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.border,
  },
  back: {
    width: 44,
    height: 44,
    borderRadius: 16,
    backgroundColor: color.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  heading: {flex: 1, gap: 3},
  title: {color: color.text, fontSize: 19, fontWeight: '600'},
  subtitle: {color: color.textSubtle, fontSize: 12, lineHeight: 18},
  content: {flexGrow: 1, padding: 16, gap: 24},
  notice: {alignItems: 'center', gap: 12, padding: 24},
  copy: {color: color.textMuted, fontSize: 14, lineHeight: 21},
  older: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: color.surface,
  },
  resting: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    paddingVertical: 24,
  },
  restingTitle: {
    fontSize: 26,
    lineHeight: 32,
    letterSpacing: -0.6,
    color: color.text,
  },
  restingCopy: {
    fontSize: 15,
    lineHeight: 23,
    textAlign: 'center',
    color: color.textMuted,
    maxWidth: 280,
  },
  prompts: {alignSelf: 'stretch', gap: 8, marginTop: 8},
  prompt: {
    minHeight: 48,
    padding: 14,
    backgroundColor: color.surface,
    borderRadius: 16,
    borderColor: color.border,
    borderWidth: StyleSheet.hairlineWidth,
  },
  error: {
    padding: 16,
    backgroundColor: color.surface,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.border,
  },
  live: {paddingHorizontal: 16, paddingTop: 8},
});
