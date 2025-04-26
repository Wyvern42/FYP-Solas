import React, { useEffect, useState, useCallback } from 'react';
import { ActivityIndicator, Image, StyleSheet, Button, RefreshControl, AppState, AppStateStatus, View } from 'react-native';
import ParallaxScrollView from '@/components/ParallaxScrollView';
import { ThemedText } from '@/components/ThemedText';
import { ThemedView } from '@/components/ThemedView';
import { useLocation } from '@/hooks/useLocation';
import { startBackgroundTracking, stopBackgroundTracking } from '@/services/backgroundTask';
import { formatTimeForDatabase } from '@/utils/timeUtils';

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
  const [feedbackTimestamp, setFeedbackTimestamp] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [dailyVisualisation, setDailyVisualisation] = useState<string | null>(null);
  const [initialLoadComplete, setInitialLoadComplete] = useState<boolean>(false);

  // Memoized function to fetch daily visualization
  const fetchDailyVisualisation = useCallback(async () => {
    if (!user_id || !sunrise || !sunset) return;
    
    try {
      const response = await fetch('http://16.170.231.125:5000/daily-visualisation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id,
          sunrise,
          sunset,
          device_time: formatTimeForDatabase(new Date())
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch daily visualization');
      }

      const data = await response.json();
      setDailyVisualisation(data.image);
    } catch (error) {
      console.error('Error fetching daily visualization:', error);
    }
  }, [user_id, sunrise, sunset]);

  // Initial load of daily visualization (only once)
  useEffect(() => {
    if (!initialLoadComplete && user_id && sunrise && sunset) {
      fetchDailyVisualisation();
      setInitialLoadComplete(true);
    }
  }, [user_id, sunrise, sunset, initialLoadComplete, fetchDailyVisualisation]);

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

  // Handle pull-to-refresh
  const onRefresh = async () => {
    setRefreshing(true);
    await fetchLocation();
    await fetchDailyVisualisation(); // Fetch new visualization on manual refresh
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
          device_time: formatTimeForDatabase(new Date())
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
      setFeedbackTimestamp(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    }
  }, [loading]);

  return (
    <ParallaxScrollView
      headerBackgroundColor={{ light: '#A1CEDC', dark: '#1D3D47' }}
      headerImage={
        <Image
          source={require('@/assets/images/sun-full-black.png')}
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
      {dailyVisualisation ? (
        <View style={styles.visualizationContainer}>
          <Image 
            source={{ uri: `data:image/png;base64,${dailyVisualisation}` }}
            style={styles.visualizationImage}
            resizeMode="contain"
          />
        </View>
      ) : (
        <ActivityIndicator size="large" color="#FFA500" />
      )}
    </ThemedView>

      <ThemedView style={styles.stepContainer}>
        <ThemedText type="subtitle">Current Status</ThemedText>
        {loading ? (
          <ActivityIndicator size="large" color="#FFA500" />
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
              <ThemedView style={{ alignItems: 'center', marginTop: 10 }}>
                <ThemedText style={{ color: '#FFA500' }}>Thank you for your feedback!</ThemedText>
                <ThemedText style={{ fontSize: 12, color: 'gray' }}>
                  Submitted at: {feedbackTimestamp}
                </ThemedText>
              </ThemedView>
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
    width: 450,
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