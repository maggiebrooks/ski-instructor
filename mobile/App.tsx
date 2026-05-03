import { useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import HomeScreen from './src/screens/HomeScreen';
import RecordScreen from './src/screens/RecordScreen';
import UploadScreen from './src/screens/UploadScreen';
import ResultsScreen from './src/screens/ResultsScreen';
import type { Screen } from './src/navigation';
import { colors } from './src/theme';

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: 'home' });

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safe} edges={['top', 'left', 'right', 'bottom']}>
        <StatusBar style="light" backgroundColor={colors.bg} />
        {screen.name === 'home' ? <HomeScreen go={setScreen} /> : null}
        {screen.name === 'record' ? <RecordScreen go={setScreen} /> : null}
        {screen.name === 'upload' ? (
          <UploadScreen
            go={setScreen}
            uri={screen.uri}
            filename={screen.filename}
            sizeBytes={screen.sizeBytes}
            durationSec={screen.durationSec}
            accelCount={screen.accelCount}
            gyroCount={screen.gyroCount}
            gpsCount={screen.gpsCount}
            baroCount={screen.baroCount}
            gpsAvailable={screen.gpsAvailable}
            sessionQuality={screen.sessionQuality}
          />
        ) : null}
        {screen.name === 'results' ? (
          <ResultsScreen go={setScreen} sessionId={screen.sessionId} />
        ) : null}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.bg,
  },
});
