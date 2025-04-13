import * as TaskManager from 'expo-task-manager';
import * as Location from 'expo-location';
import NetInfo from '@react-native-community/netinfo';
import * as SecureStore from 'expo-secure-store';
import { fetchWeatherData, fetchAstroData } from './weatherService';
import { convertTo24HourFormat, formatTimeForDatabase } from '@/utils/timeUtils';

// Define the background task name
export const LOCATION_TASK_NAME = 'background-location-task';

// Helper function to get current time in ISO format
const getCurrentTime = () => {
  return new Date().toISOString();
};

// Define the background task
TaskManager.defineTask(LOCATION_TASK_NAME, async () => {
  try {
    // Get a single, short-lived location update
    const location = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.BestForNavigation,
    });

    const { accuracy, latitude, longitude } = location.coords;

    // Check network connection
    const netInfoState = await NetInfo.fetch();
    const connectedToWifi = netInfoState.type === 'wifi';

    // Fetch weather and astronomical data
    const weatherData = await fetchWeatherData(latitude, longitude);
    const astroData = await fetchAstroData(latitude, longitude);

    // Get user ID from secure storage
    const user_id = await SecureStore.getItemAsync('user_id');

    // Send data to the database
    const response = await fetch('http://16.170.231.125:5000/check-location', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        gps_accuracy: accuracy,
        user_id,
        is_connected_to_wifi: connectedToWifi,
        weather: weatherData.current.condition.text,
        temperature: weatherData.current.temp_c,
        uv: weatherData.current.uv,
        sunrise: convertTo24HourFormat(astroData.astronomy.astro.sunrise),
        sunset: convertTo24HourFormat(astroData.astronomy.astro.sunset),
        device_time: formatTimeForDatabase(new Date())
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to send location data to the database');
    }

    console.log('Location data sent to the database successfully');
  } catch (error) {
    console.error('Error in background task:', error);
  }
});

// Function to start background tracking
export const startBackgroundTracking = async () => {
  const { status } = await Location.requestBackgroundPermissionsAsync();
  if (status === 'granted') {
    await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
      accuracy: Location.Accuracy.BestForNavigation,
      timeInterval: 5 * 60 * 1000, // 5 minutes
      distanceInterval: 100, // 100 meters
      showsBackgroundLocationIndicator: true, // Show the blue bar only during the check
    });
    console.log('Background tracking started');
  } else {
    console.error('Background location permission not granted');
  }
};

// Function to stop background tracking
export const stopBackgroundTracking = async () => {
  await Location.stopLocationUpdatesAsync(LOCATION_TASK_NAME);
  console.log('Background tracking stopped');
};