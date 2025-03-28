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

export default function WeeklyGraphScreen() {
  const { user_id } = useLocation();
  const [weeklyGraph, setWeeklyGraph] = useState<string | null>(null);
  const [dailyData, setDailyData] = useState<DailyData[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  // Function to convert seconds to HH:MM:SS format
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
    try {
      setLoading(true);
      const response = await fetch('http://16.170.231.125:5000/weekly-time-outside-graph', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user_id
        }),
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Server error response:', errorText);
        throw new Error(`Server responded with status ${response.status}`);
      }
  
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        console.error('Received non-JSON response:', text);
        throw new Error('Server did not return JSON');
      }
  
      const data = await response.json();
      if (data.image) {
        setWeeklyGraph(data.image);
      } else {
        console.error('Missing image data in response:', data);
      }

      // Combine the days and seconds arrays into an array of objects
      if (data.days && data.seconds) {
        const combinedData = data.days.map((day: string, index: number) => ({
          day,
          seconds: data.seconds[index]
        }));
        setDailyData(combinedData);
      }
    } catch (error) {
      console.error('Error fetching weekly graph:', error);
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchWeeklyGraph();
    setRefreshing(false);
  };

  useEffect(() => {
    fetchWeeklyGraph();
  }, []);

  // Render item for the FlatList
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
          source={require('@/assets/images/sun-black-bk.png')}
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
          <ActivityIndicator size="large" color="#0000ff" />
        ) : weeklyGraph ? (
          <View style={styles.visualizationContainer}>
            <Image 
              source={{ uri: `data:image/png;base64,${weeklyGraph}` }}
              style={styles.visualizationImage}
            />
          </View>
        ) : (
          <ThemedText>No weekly data available</ThemedText>
        )}
      </ThemedView>

      <ThemedView style={styles.listContainer}>
        <ThemedText type="subtitle" style={styles.listTitle}>Daily Breakdown</ThemedText>
        {dailyData.length > 0 ? (
          <FlatList
            data={dailyData}
            renderItem={renderDayItem}
            keyExtractor={(item, index) => index.toString()}
            scrollEnabled={false}
          />
        ) : (
          <ThemedText>No daily data available</ThemedText>
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
    marginBottom: 20,
  },
  graphContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  reactLogo: {
    height: 250,
    width: 400,
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
    fontSize: 16,
    fontFamily: 'monospace',
    fontWeight: '500',
  },
});