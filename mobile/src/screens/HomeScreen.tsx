import { useState } from 'react';
import { Linking, StyleSheet, Text, View } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system';

import BigButton from '../components/BigButton';
import { WEB_APP_URL } from '../config';
import type { Go } from '../navigation';
import { colors, spacing, typography } from '../theme';

type Props = { go: Go };

export default function HomeScreen({ go }: Props) {
  const [pickError, setPickError] = useState<string | null>(null);

  async function pickAndUpload() {
    setPickError(null);
    try {
      const res = await DocumentPicker.getDocumentAsync({
        // Accept ZIP from iOS Files / Android Documents.
        type: ['application/zip', 'application/x-zip-compressed', 'public.zip-archive', '*/*'],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (res.canceled) return;
      const asset = res.assets[0];
      if (!asset?.uri) {
        setPickError('Could not read the selected file.');
        return;
      }
      let size = asset.size ?? 0;
      if (!size) {
        const info = await FileSystem.getInfoAsync(asset.uri, { size: true });
        if (info.exists && 'size' in info && typeof info.size === 'number') {
          size = info.size;
        }
      }
      go({
        name: 'upload',
        uri: asset.uri,
        filename: asset.name || 'session.zip',
        sizeBytes: size,
        durationSec: 0,
        accelCount: 0,
        gyroCount: 0,
        gpsCount: 0,
        baroCount: 0,
        gpsAvailable: false,
      });
    } catch (e) {
      setPickError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <View style={styles.root}>
      <View style={styles.head}>
        <Text style={styles.title}>Ski Recorder</Text>
        <Text style={styles.subtitle}>Record IMU data, then upload for analysis.</Text>
      </View>

      <View style={styles.actions}>
        <BigButton label="Record New Session" onPress={() => go({ name: 'record' })} />
        <View style={{ height: spacing.md }} />
        <BigButton label="Upload from Files" variant="secondary" onPress={pickAndUpload} />
        {pickError ? <Text style={styles.err}>{pickError}</Text> : null}
      </View>

      <View style={styles.foot}>
        <Text style={styles.footText}>Results are shown inside this app after upload.</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    paddingBottom: spacing.lg,
    justifyContent: 'space-between',
  },
  head: {
    marginTop: spacing.lg,
  },
  title: {
    color: colors.text,
    fontSize: typography.title,
    fontWeight: '700',
  },
  subtitle: {
    color: colors.textMuted,
    fontSize: typography.subtitle,
    marginTop: spacing.sm,
  },
  actions: {
    width: '100%',
  },
  err: {
    color: colors.danger,
    fontSize: typography.body,
    marginTop: spacing.md,
  },
  foot: {
    alignItems: 'center',
  },
  footText: {
    color: colors.textMuted,
    fontSize: typography.body,
  },
  link: {
    color: colors.primary,
    marginTop: spacing.xs,
    textDecorationLine: 'underline',
  },
});
