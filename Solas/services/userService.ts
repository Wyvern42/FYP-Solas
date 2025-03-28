import * as SecureStore from 'expo-secure-store';
import uuid from 'react-native-uuid';

export const generateAndStoreUserId = async () => {
  let storedUserId = await SecureStore.getItemAsync('user_id');
  if (!storedUserId) {
    storedUserId = uuid.v4();
    await SecureStore.setItemAsync('user_id', storedUserId);
  }
  return storedUserId;
};