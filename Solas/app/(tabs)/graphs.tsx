import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Image, StyleSheet, View, RefreshControl, FlatList } from 'react-native';
import ParallaxScrollView from '@/components/ParallaxScrollView';
import { ThemedText } from '@/components/ThemedText';
import { ThemedView } from '@/components/ThemedView';
import { useLocation } from '@/hooks/useLocation';

interface DailyData {
  day: string;
  seconds: number;
}

const formatTimeForDatabase = (date: Date): string => {
  const day = date.getDate().toString().padStart(2, '0');
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const year = date.getFullYear();
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const seconds = date.getSeconds().toString().padStart(2, '0');
  return `${day}-${month}-${year} ${hours}:${minutes}:${seconds}`;
};

const formatDublinTime = (date: Date): string => {
  return date.toLocaleTimeString('en-IE', {
    timeZone: 'Europe/Dublin',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

export default function WeeklyGraphScreen() {
  const { user_id, sunrise, sunset, fetchLocation } = useLocation();
  const [weeklyGraph, setWeeklyGraph] = useState<string | null>(null);
  const [dailyData, setDailyData] = useState<DailyData[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);



  const formatTime = (totalSeconds: number): string => {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);

    return [
      hours.toString().padStart(2, '0'),
      minutes.toString().padStart(2, '0'),
      seconds.toString().padStart(2, '0')
    ].join(':');
  };

  const fetchWeeklyGraph = async () => {
    if (!user_id) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const deviceTime = formatTimeForDatabase(new Date());
      
      const response = await fetch('http://16.170.231.125:5000/weekly-time-outside-graph', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id,
          sunrise,
          sunset,
          device_time: deviceTime
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch weekly visualization');
      }

      const data = await response.json();
      setWeeklyGraph(data.image);
      
      if (data.days && data.seconds) {
        const combinedData = data.days.map((day: string, index: number) => ({
          day,
          seconds: data.seconds[index]
        }));
        setDailyData(combinedData);
      }
    } catch (error) {
      console.error('Error fetching weekly visualization:', error);
      setError('Failed to load weekly data. Pull to refresh.');
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        fetchLocation(),
        fetchWeeklyGraph()
      ]);
    } catch (error) {
      console.error('Error during refresh:', error);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchWeeklyGraph();
  }, [user_id, sunrise, sunset]);

  const renderDayItem = ({ item }: { item: DailyData }) => (
    <ThemedView style={styles.dayItem}>
      <ThemedText style={styles.dayText}>{item.day}:</ThemedText>
      <ThemedText style={styles.timeText}>{formatTime(item.seconds)}</ThemedText>
    </ThemedView>
  );

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
        <ThemedText type="title">Weekly Outdoor Time</ThemedText>
      </ThemedView>

      <ThemedView style={styles.graphContainer}>
        {loading ? (
          <ActivityIndicator size="large" color="#FFA500" />
        ) : error ? (
          <ThemedText style={{ color: 'red' }}>{error}</ThemedText>
        ) : weeklyGraph ? (
          <View style={styles.visualizationContainer}>
            <Image 
              source={{ uri: `data:image/png;base64,${weeklyGraph}` }}
              style={styles.visualizationImage}
            />
          </View>
        ) : (
          <ThemedText>No weekly data available yet</ThemedText>
        )}
      </ThemedView>

      <ThemedView style={styles.listContainer}>
        <ThemedText type="subtitle" style={styles.listTitle}>Daily Breakdown</ThemedText>
        {dailyData.length > 0 ? (
          <FlatList
            data={[...dailyData].reverse()}
            renderItem={renderDayItem}
            keyExtractor={(item, index) => index.toString()}
            scrollEnabled={false}
          />
        ) : (
          <ThemedText>No daily data available yet</ThemedText>
        )}
      </ThemedView>
    </ParallaxScrollView>
  );
}

const styles = StyleSheet.create({
  titleContainer: {
    flexDirection: 'column',
    alignItems: 'center',
    gap: 8,
    marginBottom: 20,
  },
  graphContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
    minHeight: 200,
  },
  reactLogo: {
    height: 250,
    width: 450,
    bottom: 0,
    left: 0,
    position: 'absolute',
  },
  visualizationContainer: {
    width: '130%',
    height: 200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  visualizationImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'contain',
  },
  listContainer: {
    marginTop: 20,
    paddingHorizontal: 20,
  },
  listTitle: {
    marginBottom: 15,
    textAlign: 'center',
    fontSize: 18,
    fontWeight: 'bold',
  },
  dayItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#ddd',
  },
  dayText: {
    fontSize: 16,
    fontWeight: '500',
  },
  timeText: {
    fontSize: 14,
    color: '#FFA500',
  },
});