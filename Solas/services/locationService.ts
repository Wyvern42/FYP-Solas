import * as Location from 'expo-location';
import NetInfo from '@react-native-community/netinfo';

export const requestLocationPermissions = async () => {
  const { status } = await Location.requestForegroundPermissionsAsync();
  return status;
};

export const getCurrentLocation = async () => {
  const location = await Location.getCurrentPositionAsync({});
  return location.coords;
};

export const checkWifiConnection = async () => {
  const netInfoState = await NetInfo.fetch();
  return netInfoState.type === 'wifi';
};