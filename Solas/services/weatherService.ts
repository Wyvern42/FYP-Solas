const WEATHER_API_KEY = '5949fe14755e489992a234453251702';

export const fetchWeatherData = async (latitude: number, longitude: number) => {
  const response = await fetch(
    `http://api.weatherapi.com/v1/current.json?key=${WEATHER_API_KEY}&q=${latitude},${longitude}`
  );
  return response.json();
};

export const fetchAstroData = async (latitude: number, longitude: number) => {
  const response = await fetch(
    `http://api.weatherapi.com/v1/astronomy.json?key=${WEATHER_API_KEY}&q=${latitude},${longitude}&dt=${new Date().toISOString().split('T')[0]}`
  );
  return response.json();
};