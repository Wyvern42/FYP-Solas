// utils/locationUtils.ts
import * as Location from 'expo-location';

export const getAverageLocation = async (samples: number = 3): Promise<{
  latitude: number;
  longitude: number;
  accuracy: number | null;
}> => {
  let totalLat = 0;
  let totalLng = 0;
  let totalAccuracy = 0;
  let validAccuracyReadings = 0;

  for (let i = 0; i < samples; i++) {
    try {
      const location = await Location.getCurrentPositionAsync({ 
        accuracy: Location.Accuracy.BestForNavigation 
      });
      
      totalLat += location.coords.latitude;
      totalLng += location.coords.longitude;
      
      if (location.coords.accuracy !== null) {
        totalAccuracy += location.coords.accuracy;
        validAccuracyReadings++;
      }
      
      if (i < samples - 1) {
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    } catch (error) {
      console.warn(`Error getting location sample ${i + 1}:`, error);
    }
  }

  return {
    latitude: totalLat / samples,
    longitude: totalLng / samples,
    accuracy: validAccuracyReadings > 0 ? totalAccuracy / validAccuracyReadings : null
  };
};

