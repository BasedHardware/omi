import React, {useState} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import Calendar from 'lucide-react-native/icons/calendar';
import Mail from 'lucide-react-native/icons/mail';
import Folder from 'lucide-react-native/icons/folder';
import Notebook from 'lucide-react-native/icons/notebook';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Terminal from 'lucide-react-native/icons/terminal';
import Command from 'lucide-react-native/icons/command';
import Orbit from 'lucide-react-native/icons/orbit';
import Sparkles from 'lucide-react-native/icons/sparkles';
import {
  ONBOARDING_HARNESSES,
  type HarnessKind,
} from '../app/onboardingHarnesses';
import {ShippingPressable} from './ShippingPressable';
import {ShippingStage} from './ShippingStage';
import {desktopTokens as token} from './tokens';

const artwork: Record<
  string,
  {Icon: typeof Orbit; color: string; fill: string; category: string}
> = {
  openclaw: {
    Icon: Orbit,
    color: '#ad5740',
    fill: '#f6e8e1',
    category: 'Computer use',
  },
  hermes: {
    Icon: Command,
    color: '#466e5c',
    fill: '#e5ede6',
    category: 'Automation',
  },
  claudeCode: {
    Icon: Sparkles,
    color: '#a86836',
    fill: '#f6eadb',
    category: 'Development',
  },
  codex: {
    Icon: Terminal,
    color: '#506c91',
    fill: '#e6ecf3',
    category: 'Development',
  },
  calendar: {
    Icon: Calendar,
    color: '#506c91',
    fill: '#e6ecf3',
    category: 'Your schedule',
  },
  email: {
    Icon: Mail,
    color: '#ad5740',
    fill: '#f6e8e1',
    category: 'Your inbox',
  },
  'local-files': {
    Icon: Folder,
    color: '#506c91',
    fill: '#e6ecf3',
    category: 'Your workspace',
  },
  'apple-notes': {
    Icon: Notebook,
    color: '#8b722d',
    fill: '#f3edda',
    category: 'Your ideas',
  },
  x: {
    Icon: MessageCircle,
    color: '#555b55',
    fill: '#e9eae6',
    category: 'Your interests',
  },
  chatgpt: {
    Icon: Sparkles,
    color: '#466e5c',
    fill: '#e5ede6',
    category: 'Your context',
  },
};

/** A browsable catalog, not connection state. Integrations need a real adapter
 * before this surface may offer Connect or claim that an account is connected. */
export function ConnectionGallery({kind}: {kind: HarnessKind}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [width, setWidth] = useState(0);
  const selected = ONBOARDING_HARNESSES.find(
    item => item.id === expanded && item.kind === kind,
  );
  const columns =
    width >= 600 && kind === 'context'
      ? 3
      : width === 0 || width >= 460
      ? 2
      : 1;
  return (
    <View
      style={styles.root}
      onLayout={event => setWidth(event.nativeEvent.layout.width)}>
      <View style={styles.grid}>
        {ONBOARDING_HARNESSES.filter(item => item.kind === kind).map(item => {
          const {Icon, color, fill, category} = artwork[item.id];
          const active = selected?.id === item.id;
          return (
            <View
              key={item.id}
              style={[
                styles.slot,
                {
                  width:
                    columns === 3 ? '33.333%' : columns === 2 ? '50%' : '100%',
                },
              ]}>
              <ShippingPressable
                accessibilityRole="button"
                accessibilityLabel={`Explore ${item.name}`}
                accessibilityState={{expanded: active}}
                onPress={() => setExpanded(active ? null : item.id)}
                style={[styles.card, active && styles.cardSelected]}>
                <View style={styles.cardTop}>
                  <View style={[styles.icon, {backgroundColor: fill}]}>
                    <Icon color={color} size={22} strokeWidth={1.5} />
                  </View>
                  <Text style={styles.category}>{category}</Text>
                </View>
                <Text style={styles.name}>{item.name}</Text>
                <Text style={styles.detail}>{item.detail}</Text>
                <Text style={styles.availability}>
                  {active ? 'Close details −' : 'Explore +'}
                  <Text style={styles.coming}> · Coming soon</Text>
                </Text>
              </ShippingPressable>
            </View>
          );
        })}
      </View>
      {selected ? (
        <ShippingStage
          stageKey={selected.id}
          variant="hub"
          style={styles.explanation}>
          <Text accessibilityRole="header" style={styles.explanationTitle}>
            {selected.name} in Omi
          </Text>
          <Text style={styles.detail}>
            {kind === 'agent'
              ? 'Bring your Omi context to the agents you work with.'
              : 'Bring this source into your personal context, on your terms.'}{' '}
            Setup for {selected.name} is not available in this version. No
            account has been connected and no data has been imported.
          </Text>
        </ShippingStage>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {gap: 16},
  grid: {flexDirection: 'row', flexWrap: 'wrap', margin: -6},
  slot: {padding: 6},
  card: {
    flex: 1,
    minHeight: 174,
    padding: 16,
    borderRadius: 16,
    backgroundColor: token.color.glassStrong,
    borderColor: token.color.line,
    borderWidth: 1,
    overflow: 'hidden',
  },
  cardSelected: {borderColor: token.color.inkMuted},
  cardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  icon: {
    width: 36,
    height: 36,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  category: {
    color: token.color.inkMuted,
    fontSize: 11,
    letterSpacing: 0.1,
  },
  name: {
    color: token.color.ink,
    fontSize: 17,
    fontWeight: '600',
    letterSpacing: -0.5,
    marginBottom: 6,
  },
  detail: {color: token.color.inkMuted, fontSize: 13, lineHeight: 19},
  availability: {
    color: token.color.ink,
    fontSize: 12,
    fontWeight: '600',
    marginTop: 14,
  },
  coming: {color: token.color.inkMuted, fontWeight: '400'},
  explanation: {
    flexBasis: 'auto',
    flexGrow: 0,
    flexShrink: 0,
    borderLeftWidth: 2,
    borderColor: token.color.inkMuted,
    padding: 16,
    gap: 8,
  },
  explanationTitle: {color: token.color.ink, fontSize: 15, fontWeight: '600'},
});
