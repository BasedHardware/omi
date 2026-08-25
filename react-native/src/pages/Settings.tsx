import React, {useState} from 'react';
import {ScrollView, Text, View} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';

export function SettingsPage() {
  const [section, setSection] = useState('Account');
  return (
    <ScrollView contentContainerStyle={styles.destinationPage}>
      <Text style={styles.projectionTitle}>Settings</Text>
      <View accessibilityRole="tablist" style={styles.destinationTabs}>
        {['Account', 'Privacy', 'Developer'].map(label => (
          <FocusPressable
            accessibilityLabel={`${label} settings`}
            accessibilityRole="tab"
            accessibilityState={{selected: section === label}}
            key={label}
            onPress={() => setSection(label)}
            style={({pressed}) => [
              styles.destinationTab,
              section === label && styles.destinationTabActive,
              pressed && styles.pressed,
            ]}>
            <Text
              style={[
                styles.destinationTabText,
                section === label && styles.destinationTabTextActive,
              ]}>
              {label}
            </Text>
          </FocusPressable>
        ))}
      </View>
      <View style={styles.destinationSection}>
        <Text style={styles.destinationSectionTitle}>{section}</Text>
        <Text style={styles.destinationUnavailable}>
          {section} settings unavailable
        </Text>
        <Text style={styles.projectionEmptyCopy}>
          {section === 'Account'
            ? 'Profile, plan, notification, and usage settings require authenticated account APIs that the v5 backend does not expose.'
            : section === 'Privacy'
            ? 'Recording, training, export, and deletion settings require authenticated privacy APIs that the v5 backend does not expose.'
            : 'API keys, webhooks, and developer exports require authenticated developer APIs that the v5 backend does not expose.'}
        </Text>
        <Text style={styles.projectionEmptyCopy}>
          No settings were inferred or changed.
        </Text>
      </View>
    </ScrollView>
  );
}
