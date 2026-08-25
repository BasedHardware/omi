import React, {forwardRef} from 'react';
import {
  type StyleProp,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  type TextStyle,
  View,
  type ViewStyle,
} from 'react-native';
import {tokens} from './tokens';

export type InputProps = Omit<TextInputProps, 'style'> & {
  containerStyle?: StyleProp<ViewStyle>;
  invalid?: boolean;
  leading?: React.ReactNode;
  style?: StyleProp<TextStyle>;
  trailing?: React.ReactNode;
};

export const Input = forwardRef<TextInput, InputProps>(function Input(
  {
    accessibilityState,
    containerStyle,
    editable = true,
    invalid = false,
    leading,
    placeholderTextColor = tokens.color.textSubtle,
    selectionColor = tokens.color.focus,
    style,
    trailing,
    ...props
  },
  ref,
) {
  return (
    <View
      style={[
        styles.inputFrame,
        invalid && styles.inputFrameInvalid,
        !editable && styles.disabled,
        containerStyle,
      ]}>
      {leading}
      <TextInput
        {...props}
        accessibilityState={accessibilityState}
        aria-invalid={invalid}
        editable={editable}
        placeholderTextColor={placeholderTextColor}
        ref={ref}
        selectionColor={selectionColor}
        style={[styles.input, style]}
      />
      {trailing}
    </View>
  );
});

export type FieldProps = InputProps & {
  error?: string;
  hint?: string;
  label?: string;
};

export const Field = forwardRef<TextInput, FieldProps>(function Field(
  {error, hint, label, ...props},
  ref,
) {
  return (
    <View style={styles.field}>
      {label === undefined ? null : <Text style={styles.label}>{label}</Text>}
      <Input {...props} invalid={error !== undefined} ref={ref} />
      {error === undefined && hint !== undefined ? (
        <Text style={styles.hint}>{hint}</Text>
      ) : null}
      {error === undefined ? null : <Text style={styles.error}>{error}</Text>}
    </View>
  );
});

const styles = StyleSheet.create({
  field: {gap: tokens.space.xs},
  label: {color: tokens.color.text, ...tokens.type.label},
  inputFrame: {
    alignItems: 'center',
    backgroundColor: tokens.color.input,
    borderColor: tokens.color.line,
    borderRadius: tokens.radius.md,
    borderWidth: tokens.border.width,
    flexDirection: 'row',
    gap: tokens.space.sm,
    minHeight: tokens.size.control,
    paddingHorizontal: tokens.space.md,
  },
  inputFrameInvalid: {borderColor: tokens.color.danger},
  input: {
    color: tokens.color.text,
    flex: tokens.layout.grow,
    padding: tokens.space.none,
    ...tokens.type.body,
  },
  hint: {color: tokens.color.textMuted, ...tokens.type.caption},
  error: {color: tokens.color.danger, ...tokens.type.caption},
  disabled: {opacity: tokens.opacity.disabled},
});
