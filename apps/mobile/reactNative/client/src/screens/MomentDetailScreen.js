import {useContext, useState, useEffect} from 'react';
import {ScrollView, View, Text, StyleSheet} from 'react-native';
import {Card} from 'react-native-elements';
import {MomentsContext} from '../contexts/MomentsContext';

const MomentDetailScreen = ({route}) => {
  const {momentId} = route.params;
  const {moments} = useContext(MomentsContext);
  const [moment, setMoment] = useState(null);

  useEffect(() => {
    const foundMoment = moments.find(m => m.id === momentId);
    setMoment(foundMoment);
  }, [moments, momentId]);

  if (!moment) {
    return <Text>Loading...</Text>;
  }

  return (
    <ScrollView
      style={{backgroundColor: '#000'}}
      contentContainerStyle={styles.container}>
      <Card containerStyle={styles.card}>
        <Card.Title style={styles.title}>{moment.title}</Card.Title>
        <Card.Divider />
        <Text style={styles.title}>Summary</Text>
        <Text style={styles.summaryText}>{moment.summary}</Text>
        <Card.Divider />
        <Text style={styles.title}>Action Items</Text>
        <Text style={styles.actionItems}>
          {moment.actionItems.map((item, index) => (
            <Text key={index} style={styles.actionItemsText}>
              • {item}
              {'\n'}
            </Text>
          ))}
        </Text>
        <Card.Divider />
        <View style={styles.transcriptContainer}>
          <Text style={styles.title}>Transcript</Text>
          <ScrollView>
            <Text style={styles.transcriptText}>{moment.transcript}</Text>
          </ScrollView>
        </View>
      </Card>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 10,
    backgroundColor: '#000', // Light grey background
  },
  card: {
    borderRadius: 10,
    shadowOpacity: 0.2,
    shadowRadius: 5,
    shadowColor: '#000',
    shadowOffset: {height: 2, width: 2},
    marginBottom: 10,
    padding: 10,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 5,
  },
  summaryText: {
    fontSize: 18,
    color: '#333',
    marginBottom: 10,
  },
  actionItemsText: {
    fontSize: 18,
    color: '#333',
    marginBottom: 10,
  },
  transcriptContainer: {
    minHeight: 100,
    maxHeight: 400,
    overflow: 'hidden',
    backgroundColor: '#fff',
  },
  transcriptText: {
    fontSize: 16,
  },
});

export default MomentDetailScreen;
