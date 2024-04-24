import React from 'react';
import { ScrollView, View, Text, StyleSheet } from 'react-native';
import { Card } from 'react-native-elements';

const MomentDetailScreen = ({ route }) => {
  const { transcript, summary } = route.params;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Card>
        <Card.Title>Transcript Summary</Card.Title>
        <Card.Divider />
        <Text style={styles.summaryText}>{summary}</Text>
      </Card>

      <View style={styles.transcriptContainer}>
        <ScrollView>
          <Text style={styles.transcriptText}>{transcript}</Text>
        </ScrollView>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 10,
  },
  transcriptContainer: {
    minHeight: 100,
    maxHeight: 400,
    overflow: 'hidden',
  },
  transcriptText: {
    fontSize: 16,
    padding: 10,
  },
  summaryText: {
    fontSize: 18,
    padding: 10,
  }
});

export default MomentDetailScreen;