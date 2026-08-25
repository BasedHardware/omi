import React from 'react';
import {ScrollView, Text, View} from 'react-native';
import {styles} from '../ui/styles';

export function ConnectorsPage() {
  return (
    <ScrollView contentContainerStyle={styles.destinationPage}>
      <Text style={styles.projectionTitle}>Connectors</Text>
      <Text style={styles.destinationIntro}>
        Apps and external services belong together here.
      </Text>
      <View style={styles.destinationSections}>
        {['Explore', 'Installed', 'My Apps', 'Services'].map(label => (
          <View key={label} style={styles.destinationSection}>
            <Text style={styles.destinationSectionTitle}>{label}</Text>
            <Text style={styles.projectionEmptyCopy}>
              {label === 'Services'
                ? 'External service connections are unavailable because the v5 backend does not expose connector authorization.'
                : 'App records are unavailable because the v5 backend does not expose an app catalogue or installations.'}
            </Text>
          </View>
        ))}
      </View>
      <Text style={styles.destinationUnavailable}>Connectors unavailable</Text>
      <Text style={styles.projectionEmptyCopy}>
        No connector records or connection controls are shown.
      </Text>
    </ScrollView>
  );
}
