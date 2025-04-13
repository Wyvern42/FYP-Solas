import { useEffect, useState } from 'react';
import * as Location from 'expo-location';
import NetInfo from '@react-native-community/netinfo';
import { fetchWeatherData, fetchAstroData } from '@/services/weatherService';
import { generateAndStoreUserId } from '@/services/userService';
import { convertTo24HourFormat, formatTimeForDatabase } from '@/utils/timeUtils';

export const useLocation = () => {
  const [isOutside, setIsOutside] = useState<boolean | null>(null);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isConnectedToWifi, setIsConnectedToWifi] = useState<boolean>(false);
  const [user_id, setUser_id] = useState<string | null>(null);
  const [weather, setWeather] = useState<string | null>(null);
  const [temperature, setTemperature] = useState<number | null>(null);
  const [uv, setUv] = useState<number | null>(null);
  const [sunrise, setSunrise] = useState<string | null>(null);
  const [sunset, setSunset] = useState<string | null>(null);

  // Helper function to get current time in ISO format
  const getCurrentTime = () => {
    return new Date().toISOString();
  };

  const fetchLocation = async () => {
    if (!user_id) return;

    setLoading(true);
    setError(null);

    try {
      const connectedToWifi = await NetInfo.fetch().then(state => state.type === 'wifi');
      setIsConnectedToWifi(connectedToWifi);

      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setError('Permission to access location was denied');
        return;
      }

      const location = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.BestForNavigation });
      setAccuracy(location.coords.accuracy);

      const weatherData = await fetchWeatherData(location.coords.latitude, location.coords.longitude);
      setWeather(weatherData.current.condition.text);
      setTemperature(weatherData.current.temp_c);
      setUv(weatherData.current.uv);

      const astroData = await fetchAstroData(location.coords.latitude, location.coords.longitude);
      setSunrise(convertTo24HourFormat(astroData.astronomy.astro.sunrise));
      setSunset(convertTo24HourFormat(astroData.astronomy.astro.sunset));

      const response = await fetch('http://16.170.231.125:5000/check-location', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          gps_accuracy: location.coords.accuracy,
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
        throw new Error('Failed to fetch location status');
      }

      const data = await response.json();
      setIsOutside(data.is_outside);
    } catch (error) {
      console.error('Error fetching location:', error);
      setError('Failed to determine location status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    generateAndStoreUserId().then((id) => {
      setUser_id(id);
      fetchLocation();
    });

    const interval = setInterval(() => {
      fetchLocation();
    }, 5 * 60 * 1000); // Fetch location every 5 minutes

    return () => clearInterval(interval);
  }, [user_id]);

  return {
    isOutside,
    accuracy,
    loading,
    error,
    isConnectedToWifi,
    user_id,
    weather,
    temperature,
    uv,
    sunrise,
    sunset,
    fetchLocation, 
  };
};