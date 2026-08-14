import React, {useEffect, useRef, useState} from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import Brain from 'lucide-react-native/icons/brain';
import GanttChartSquare from 'lucide-react-native/icons/square-chart-gantt';
import House from 'lucide-react-native/icons/house';
import ListChecks from 'lucide-react-native/icons/list-checks';
import Mic from 'lucide-react-native/icons/mic';
import Paperclip from 'lucide-react-native/icons/paperclip';
import {
  loadChatHistory,
  sendChatMessage,
  type ChatMessage,
} from './src/chatClient';
import {omiBackend} from './src/omiNative';

type NavigationIcon = React.ComponentType<{
  color?: string;
  size?: number;
  strokeWidth?: number;
}>;

const navigation: Array<{label: string; icon: NavigationIcon}> = [
  {label: 'Home', icon: House},
  {label: 'Conversations', icon: GanttChartSquare},
  {label: 'Memories', icon: Brain},
  {label: 'Tasks', icon: ListChecks},
];
const quickPrompts = [
  'What did I talk about today?',
  'Show my pending tasks',
  'What should I remember?',
  'Summarize my recent conversations',
];
type Route = 'Home' | 'Conversations' | 'Memories' | 'Tasks';

function NavItem({
  label,
  icon: Icon,
  compact,
  active,
  onPress,
}: {
  label: string;
  icon: NavigationIcon;
  compact: boolean;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityState={{selected: active}}
      onPress={onPress}
      style={({pressed}) => [
        styles.navItem,
        compact && styles.navItemCompact,
        active && styles.navItemActive,
        pressed && styles.pressed,
      ]}>
      <Icon color={active ? '#141414' : '#888888'} size={20} strokeWidth={2} />
      <Text
        numberOfLines={1}
        style={[styles.navText, active && styles.navTextActive]}>
        {label}
      </Text>
    </Pressable>
  );
}

function OmiMark() {
  return (
    <View accessibilityLabel="Omi" style={styles.mark}>
      <View style={[styles.markBar, styles.markBarShort]} />
      <View style={[styles.markBar, styles.markBarTall]} />
      <View style={[styles.markBar, styles.markBarMedium]} />
      <View style={[styles.markBar, styles.markBarTall]} />
      <View style={[styles.markBar, styles.markBarShort]} />
    </View>
  );
}

function ProjectionPage({route}: {route: Exclude<Route, 'Home'>}) {
  const copy = {
    Conversations: 'Conversation history is unavailable in this build.',
    Memories: 'Memory history is unavailable in this build.',
    Tasks: 'Task history is unavailable in this build.',
  }[route];

  return (
    <View style={styles.projection}>
      <Text style={styles.projectionTitle}>{route}</Text>
      <View style={styles.projectionEmpty}>
        <Text style={styles.projectionEmptyTitle}>Nothing to show yet</Text>
        <Text style={styles.projectionEmptyCopy}>{copy}</Text>
      </View>
    </View>
  );
}

function App(): React.JSX.Element {
  const {width} = useWindowDimensions();
  const compact = width < 760;
  const stageOpacity = useRef(new Animated.Value(0)).current;
  const stageTranslateY = useRef(new Animated.Value(8)).current;
  const mobileNavOpacity = useRef(new Animated.Value(0)).current;
  const mobileNavTranslateY = useRef(new Animated.Value(100)).current;
  const [reduceMotion, setReduceMotion] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [route, setRoute] = useState<Route>('Home');

  useEffect(() => {
    let active = true;
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      return () => undefined;
    }
    loadChatHistory(backend)
      .then(history => {
        if (active) {
          setMessages(history);
        }
      })
      .catch(() => {
        if (active) {
          setChatError('Chat is temporarily unavailable.');
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled().then(enabled => {
      if (active) {
        setReduceMotion(enabled);
      }
    });
    const subscription = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      setReduceMotion,
    );
    return () => {
      active = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    stageOpacity.setValue(0);
    stageTranslateY.setValue(reduceMotion ? 0 : 8);
    Animated.parallel([
      Animated.timing(stageOpacity, {
        duration: reduceMotion ? 1 : 250,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(stageTranslateY, {
        duration: reduceMotion ? 1 : 250,
        easing: Easing.out(Easing.cubic),
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [reduceMotion, route, stageOpacity, stageTranslateY]);

  useEffect(() => {
    if (!compact) {
      mobileNavOpacity.setValue(1);
      mobileNavTranslateY.setValue(0);
      return;
    }
    mobileNavOpacity.setValue(0);
    mobileNavTranslateY.setValue(reduceMotion ? 0 : 100);
    Animated.parallel([
      Animated.timing(mobileNavOpacity, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(mobileNavTranslateY, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [compact, mobileNavOpacity, mobileNavTranslateY, reduceMotion]);

  const nav = (
    <Animated.View
      accessibilityRole="tablist"
      style={[
        styles.navigation,
        compact ? styles.bottomNav : styles.rail,
        compact && {
          opacity: mobileNavOpacity,
          transform: [{translateY: mobileNavTranslateY}],
        },
      ]}>
      {!compact && <Text style={styles.wordmark}>omi</Text>}
      <View style={[styles.navItems, compact && styles.navItemsCompact]}>
        {navigation.map(item => (
          <NavItem
            active={route === item.label}
            compact={compact}
            icon={item.icon}
            key={item.label}
            label={item.label}
            onPress={() => setRoute(item.label as Route)}
          />
        ))}
      </View>
    </Animated.View>
  );

  const send = async () => {
    const text = draft.trim();
    const backend = omiBackend;
    if (backend === undefined || backend === null || text === '' || chatBusy) {
      return;
    }
    setChatBusy(true);
    setChatError(null);
    try {
      const result = await sendChatMessage(backend, text);
      setMessages(current => [
        ...current.filter(message => message.id !== result.human.id),
        result.human,
        ...(result.assistant === null ? [] : [result.assistant]),
      ]);
      setDraft('');
    } catch {
      setChatError('Message not sent. Try again.');
      try {
        setMessages(await loadChatHistory(backend));
      } catch {}
    } finally {
      setChatBusy(false);
    }
  };

  const composer = (
    <View style={styles.composerWrap}>
      <View style={styles.composer}>
        <TextInput
          accessibilityLabel="Ask Omi"
          multiline
          onChangeText={setDraft}
          placeholder="Ask anything..."
          placeholderTextColor="#888888"
          style={styles.composerInput}
          value={draft}
        />
        <View style={styles.composerActions}>
          <Pressable
            accessibilityLabel="Attach file unavailable"
            accessibilityRole="button"
            disabled
            style={({pressed}) => [
              styles.iconButton,
              pressed && styles.pressed,
            ]}>
            <Paperclip color="#666666" size={18} strokeWidth={2} />
          </Pressable>
          <Pressable
            accessibilityLabel="Dictation unavailable"
            accessibilityRole="button"
            disabled
            style={({pressed}) => [
              styles.iconButton,
              pressed && styles.pressed,
            ]}>
            <Mic color="#666666" size={18} strokeWidth={2} />
          </Pressable>
          <View style={styles.actionSpacer} />
          <Pressable
            accessibilityLabel={
              omiBackend === undefined || omiBackend === null
                ? 'Send message unavailable'
                : 'Send message'
            }
            accessibilityRole="button"
            disabled={
              omiBackend === undefined ||
              omiBackend === null ||
              draft.trim() === '' ||
              chatBusy
            }
            onPress={send}
            style={({pressed}) => [
              styles.sendButton,
              pressed && styles.pressed,
            ]}>
            <ArrowUp color="#141414" size={18} strokeWidth={2.5} />
          </Pressable>
        </View>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.outer}>
      <View style={[styles.shell, !compact && styles.shellWide]}>
        {!compact && nav}
        <View style={[styles.paneInset, compact && styles.paneInsetCompact]}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={[styles.pane, compact && styles.paneCompact]}>
            <Animated.View
              accessibilityLabel={`${route} stage`}
              style={[
                styles.stageMotion,
                {
                  opacity: stageOpacity,
                  transform: [{translateY: stageTranslateY}],
                },
              ]}>
              <View style={styles.stage}>
                {route === 'Home' ? (
                  <View style={styles.home}>
                    <OmiMark />
                    <Text style={styles.greeting}>I’m ready.</Text>
                    <View style={styles.currents}>
                      <Text style={styles.sectionLabel}>CURRENTS</Text>
                      {messages.length === 0 &&
                      !chatBusy &&
                      chatError === null ? (
                        <Text style={styles.empty}>
                          Nothing’s waiting on you.
                        </Text>
                      ) : (
                        <View style={styles.transcript}>
                          {messages.map(message => (
                            <Text
                              key={message.id}
                              style={[
                                styles.message,
                                message.sender === 'human' &&
                                  styles.humanMessage,
                              ]}>
                              {message.text}
                            </Text>
                          ))}
                          {chatBusy && (
                            <Text style={styles.empty}>Thinking…</Text>
                          )}
                          {chatError !== null && (
                            <Text style={styles.error}>{chatError}</Text>
                          )}
                        </View>
                      )}
                    </View>
                    <View style={styles.prompts}>
                      {quickPrompts.map(prompt => (
                        <Pressable
                          accessibilityRole="button"
                          key={prompt}
                          onPress={() => setDraft(prompt)}
                          style={({pressed}) => [
                            styles.promptChip,
                            pressed && styles.pressed,
                          ]}>
                          <Text style={styles.promptText}>{prompt}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                ) : (
                  <ProjectionPage route={route} />
                )}
              </View>
            </Animated.View>
            {route === 'Home' && composer}
          </KeyboardAvoidingView>
        </View>
        {compact && nav}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  outer: {backgroundColor: '#141414', flex: 1},
  shell: {backgroundColor: '#141414', flex: 1},
  shellWide: {flexDirection: 'row'},
  navigation: {backgroundColor: '#141414'},
  rail: {paddingHorizontal: 14, paddingVertical: 20, width: 216},
  wordmark: {
    color: '#ffffff',
    fontSize: 25,
    fontWeight: '900',
    letterSpacing: -1,
    paddingHorizontal: 12,
  },
  navItems: {gap: 4, marginTop: 44},
  navItemsCompact: {flexDirection: 'row', marginTop: 0},
  navItem: {
    alignItems: 'center',
    borderRadius: 12,
    flexDirection: 'row',
    gap: 12,
    minHeight: 48,
    paddingHorizontal: 14,
  },
  navItemCompact: {
    flex: 1,
    flexDirection: 'column',
    gap: 2,
    justifyContent: 'center',
    paddingHorizontal: 2,
  },
  navItemActive: {backgroundColor: '#ffffff'},
  navText: {color: '#b0b0b0', fontSize: 14, fontWeight: '600'},
  navTextActive: {color: '#141414'},
  bottomNav: {
    borderTopColor: '#2a2a2a',
    borderTopWidth: 1,
    paddingHorizontal: 4,
    paddingTop: 4,
  },
  paneInset: {flex: 1, padding: 12, paddingLeft: 0},
  paneInsetCompact: {padding: 0},
  pane: {
    backgroundColor: '#1a1a1a',
    borderColor: '#303030',
    borderRadius: 26,
    borderWidth: 1,
    flex: 1,
    overflow: 'hidden',
  },
  paneCompact: {borderRadius: 0, borderWidth: 0},
  stageMotion: {flex: 1},
  stage: {flexGrow: 1, paddingBottom: 20, paddingHorizontal: 20},
  home: {
    alignSelf: 'center',
    flex: 1,
    justifyContent: 'center',
    maxWidth: 560,
    minHeight: 500,
    paddingVertical: 40,
    width: '100%',
  },
  mark: {
    alignItems: 'center',
    alignSelf: 'center',
    flexDirection: 'row',
    gap: 3,
    height: 34,
  },
  markBar: {backgroundColor: '#ffffff', borderRadius: 4, width: 5},
  markBarShort: {height: 11},
  markBarMedium: {height: 20},
  markBarTall: {height: 30},
  greeting: {
    color: '#ffffff',
    fontSize: 25,
    fontWeight: '600',
    marginTop: 20,
    textAlign: 'center',
  },
  currents: {marginTop: 34, width: '100%'},
  sectionLabel: {
    color: '#888888',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
    marginBottom: 12,
  },
  prompts: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    justifyContent: 'center',
    marginTop: 28,
  },
  promptChip: {
    alignItems: 'center',
    backgroundColor: '#252525',
    borderColor: '#363636',
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 14,
  },
  promptText: {color: '#e5e5e5', fontSize: 13, fontWeight: '500'},
  empty: {color: '#666666', fontSize: 12, textAlign: 'center'},
  transcript: {gap: 10},
  message: {color: '#e5e5e5', fontSize: 14, lineHeight: 20},
  humanMessage: {color: '#ffffff', fontWeight: '600'},
  error: {color: '#d8a0a0', fontSize: 12, textAlign: 'center'},
  projection: {flex: 1, paddingHorizontal: 28, paddingVertical: 24},
  projectionTitle: {color: '#ffffff', fontSize: 22, fontWeight: '600'},
  projectionEmpty: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    paddingBottom: 48,
  },
  projectionEmptyTitle: {color: '#e5e5e5', fontSize: 16, fontWeight: '600'},
  projectionEmptyCopy: {
    color: '#888888',
    fontSize: 14,
    lineHeight: 20,
    marginTop: 8,
    textAlign: 'center',
  },
  composerWrap: {paddingBottom: 16, paddingHorizontal: 20, paddingTop: 12},
  composer: {
    alignSelf: 'center',
    backgroundColor: '#252525',
    borderColor: '#3a3a3a',
    borderRadius: 28,
    borderWidth: 1,
    maxWidth: 820,
    minHeight: 62,
    paddingHorizontal: 10,
    paddingVertical: 7,
    width: '100%',
  },
  composerInput: {
    color: '#ffffff',
    fontSize: 16,
    maxHeight: 140,
    minHeight: 44,
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  composerActions: {alignItems: 'center', flexDirection: 'row'},
  iconButton: {
    alignItems: 'center',
    borderRadius: 20,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  actionSpacer: {flex: 1},
  sendButton: {
    alignItems: 'center',
    backgroundColor: '#555555',
    borderRadius: 20,
    height: 44,
    justifyContent: 'center',
    opacity: 0.35,
    width: 44,
  },
  pressed: {opacity: 0.72, transform: [{scale: 0.98}]},
});

export default App;
