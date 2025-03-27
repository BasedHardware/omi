import React, { useState } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, SafeAreaView } from 'react-native';
import { echo } from 'omi-react-native';

export default function App() {
  const [response, setResponse] = useState<string | null>(null);

  const handlePress = () => {
    const result = echo('Hello Omi!');
    setResponse(result);
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.title}>Omi SDK Example</Text>
        
        <TouchableOpacity 
          style={styles.button} 
          onPress={handlePress}
        >
          <Text style={styles.buttonText}>Say Hello</Text>
        </TouchableOpacity>
        
        {response && (
          <View style={styles.responseContainer}>
            <Text style={styles.responseTitle}>Response:</Text>
            <Text style={styles.responseText}>{response}</Text>
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 40,
    color: '#333',
  },
  button: {
    backgroundColor: '#007AFF',
    paddingVertical: 12,
    paddingHorizontal: 30,
    borderRadius: 25,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  buttonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '600',
  },
  responseContainer: {
    marginTop: 40,
    padding: 20,
    backgroundColor: 'white',
    borderRadius: 10,
    width: '100%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
    elevation: 2,
  },
  responseTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
    color: '#555',
  },
  responseText: {
    fontSize: 16,
    color: '#333',
  },
});
