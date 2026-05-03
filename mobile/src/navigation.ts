import type { SessionQualityFile } from './lib/csv';

// Tiny state-based router so we don't pull in react-navigation for a handful
// of screens.
export type Screen =
  | { name: 'home' }
  | { name: 'record' }
  | { name: 'results'; sessionId: string }
  | {
      name: 'upload';
      uri: string;
      filename: string;
      sizeBytes: number;
      durationSec: number;
      accelCount: number;
      gyroCount: number;
      gpsCount: number;
      baroCount: number;
      gpsAvailable: boolean;
      /** Present when the ZIP was built in-app after recording. */
      sessionQuality?: SessionQualityFile;
    };

export type Go = (s: Screen) => void;
