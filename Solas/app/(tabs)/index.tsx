import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Image, StyleSheet, Button, RefreshControl, AppState, AppStateStatus, View } from 'react-native';
import { HelloWave } from '@/components/HelloWave';
import ParallaxScrollView from '@/components/ParallaxScrollView';
import { ThemedText } from '@/components/ThemedText';
import { ThemedView } from '@/components/ThemedView';
import { useLocation } from '@/hooks/useLocation';
import { startBackgroundTracking, stopBackgroundTracking } from '@/services/backgroundTask';

export default function HomeScreen() {
  const {
    isOutside,
    accuracy,
    loading,
    error,
    isConnectedToWifi,
    user_id,
    sunrise,
    sunset,
    fetchLocation,
  } = useLocation();

  const [feedbackSubmitted, setFeedbackSubmitted] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [dailyVisualization, setDailyVisualization] = useState<string | null>(null);

  // Start background tracking when the app loads
  useEffect(() => {
    startBackgroundTracking();
    
    // Cleanup: Stop background tracking when the component unmounts
    return () => {
      stopBackgroundTracking();
    };
  }, []);

  // Handle app state changes (foreground/background)
  useEffect(() => {
    const handleAppStateChange = (nextAppState: AppStateStatus) => {
      if (nextAppState === 'background') {
        startBackgroundTracking();
      } else if (nextAppState === 'active') {
        stopBackgroundTracking();
      }
    };

    const subscription = AppState.addEventListener('change', handleAppStateChange);

    return () => {
      subscription.remove();
    };
  }, []);

  // Fetch daily visualization when user_id or sunrise/sunset changes
  useEffect(() => {
    const fetchDailyVisualization = async () => {
      if (!user_id || !sunrise || !sunset) return;
      
      try {
        const response = await fetch('http://16.170.231.125:5000/daily-visualization', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            user_id,
            sunrise,
            sunset
          }),
        });

        if (!response.ok) {
          throw new Error('Failed to fetch daily visualization');
        }

        const data = await response.json();
        setDailyVisualization(data.image);
      } catch (error) {
        console.error('Error fetching daily visualization:', error);
      }
    };

    fetchDailyVisualization();
  }, [user_id, sunrise, sunset]);

  // Handle pull-to-refresh
  const onRefresh = async () => {
    setRefreshing(true);
    await fetchLocation();
    setRefreshing(false);
  };

  // Submit feedback to the server
  const submitFeedback = async (correctResult: boolean) => {
    try {
      const response = await fetch('http://16.170.231.125:5000/submit-feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user_id,
          correct_result: correctResult,
          gps_accuracy: accuracy,
        }),
      });

      const data = await response.json();
      if (response.ok) {
        setFeedbackSubmitted(true);
      } else {
        console.error('Error submitting feedback:', data.error);
      }
    } catch (error) {
      console.error('Error submitting feedback:', error);
    }
  };

  // Reset feedback buttons when a new location check happens
  useEffect(() => {
    if (!loading) {
      setFeedbackSubmitted(false);
    }
  }, [loading]);

  return (
    <ParallaxScrollView
      headerBackgroundColor={{ light: '#A1CEDC', dark: '#1D3D47' }}
      headerImage={
        <Image
          source={require('@/assets/images/sun-black-bk.png')}
          style={styles.reactLogo}
        />
      }
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      <ThemedView style={styles.titleContainer}>
        <ThemedText type="title">Solas 🔆</ThemedText>
      </ThemedView>

      <ThemedView style={styles.stepContainer}>
        
        {dailyVisualization ? (
          <View style={styles.visualizationContainer}>
            <Image 
              source={{ uri: `data:image/png;base64,${dailyVisualization}` }}
              style={styles.visualizationImage}
              resizeMode="contain"
            />
          </View>
        ) : (
          <ActivityIndicator size="large" color="#0000ff" />
        )}
      </ThemedView>

      <ThemedView style={styles.stepContainer}>
        <ThemedText type="subtitle">Current Status</ThemedText>
        {loading ? (
          <ActivityIndicator size="small" color="#0000ff" />
        ) : error ? (
          <ThemedText style={{ color: 'red' }}>{error}</ThemedText>
        ) : (
          <>
            <ThemedText>
              You are currently {isOutside ? 'outside' : 'inside'}.
            </ThemedText>
            <ThemedText>
              GPS Accuracy: {accuracy !== null ? `${accuracy.toFixed(2)} meters` : 'N/A'}
            </ThemedText>
            <ThemedText>
              Connected to Wi-Fi: {isConnectedToWifi ? 'Yes' : 'No'}
            </ThemedText>
            {!feedbackSubmitted && (
              <View style={{flexDirection: 'row', justifyContent: 'center'}}>
                <Button title="Correct" color="#FFA500" onPress={() => submitFeedback(true)} />
                <Button title="Incorrect" color="#FFA500" onPress={() => submitFeedback(false)} />
              </View>
            )}
            {feedbackSubmitted && (
              <ThemedText style={{ color: 'green' }}>Thank you for your feedback!</ThemedText>
            )}
          </>
        )}
      </ThemedView>
    </ParallaxScrollView>
  );
}

const styles = StyleSheet.create({
  titleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  stepContainer: {
    gap: 8,
    marginBottom: 8,
    alignItems: 'center',
  },
  reactLogo: {
    height: 250,
    width: 400,
    bottom: 0,
    left: 0,
    position: 'absolute',
  },
  visualizationContainer: {
    width: '100%',
    height: 200,  
    justifyContent: 'center',
    alignItems: 'center',
    marginVertical: 10,
  },
  visualizationImage: {
    width: '100%',
    height: '100%',
  },
  totalTimeText: {
    fontSize: 18,
    fontWeight: 'bold',
    marginTop: 10,
  },
});