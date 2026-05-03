import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, radii, spacing, typography } from '../theme';

type Variant = 'primary' | 'danger' | 'secondary';

type Props = {
  label: string;
  onPress: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  testID?: string;
};

export default function BigButton({
  label,
  onPress,
  variant = 'primary',
  disabled,
  loading,
  testID,
}: Props) {
  const isDisabled = disabled || loading;
  const palette = paletteFor(variant);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!isDisabled, busy: !!loading }}
      testID={testID}
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.btn,
        {
          backgroundColor: palette.bg,
          borderColor: palette.border,
          opacity: isDisabled ? 0.55 : pressed ? 0.85 : 1,
        },
      ]}
    >
      <View style={styles.row}>
        {loading ? <ActivityIndicator color={palette.text} /> : null}
        <Text style={[styles.label, { color: palette.text }]}>{label}</Text>
      </View>
    </Pressable>
  );
}

function paletteFor(variant: Variant): {
  bg: string;
  text: string;
  border: string;
} {
  switch (variant) {
    case 'danger':
      return { bg: colors.danger, text: colors.text, border: colors.danger };
    case 'secondary':
      return { bg: colors.surface, text: colors.text, border: colors.border };
    case 'primary':
    default:
      return { bg: colors.primary, text: colors.text, border: colors.primary };
  }
}

const styles = StyleSheet.create({
  btn: {
    minHeight: 56,
    borderRadius: radii.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  label: {
    fontSize: typography.button,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
});
