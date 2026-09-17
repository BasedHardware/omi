import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  disableCloudApp,
  enableCloudApp,
  exploreApps,
  installedApps,
  loadConnectors,
  myApps,
  serviceApps,
  cloudSessionUnavailableCopy,
  type CloudApp,
  type ConnectorsSnapshot,
} from '../desktopCloudClient';
import {
  desktopBackendConfigurationCopy,
  desktopBackendServiceCopy,
  desktopBackendUnauthorizedCopy,
  desktopReadErrorCopy,
} from '../desktopReadClient';
import {omiAuth, omiBackend} from '../omiNative';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';
import {mobileColor} from '../mobile/mobileTokens';
import Puzzle from 'lucide-react-native/icons/puzzle';

const catalogTabs = ['Explore', 'Installed', 'My Apps', 'Services'] as const;

export function ConnectorsPage({
  onSignIn,
  signingIn = false,
}: {
  onSignIn?: () => Promise<void>;
  signingIn?: boolean;
}) {
  const [phase, setPhase] = useState<
    'loading' | 'signed-out' | 'ready' | 'error'
  >('loading');
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<ConnectorsSnapshot | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [catalogTab, setCatalogTab] =
    useState<(typeof catalogTabs)[number]>('Explore');

  const reload = useCallback(async () => {
    if (Platform.OS === 'web') {
      setSnapshot(null);
      setError('Apps are not available for this browser connection yet.');
      setPhase('error');
      return;
    }
    const backend = omiBackend;
    const auth = omiAuth;
    setActionError(null);
    if (backend === undefined || backend === null) {
      setSnapshot(null);
      setError(cloudSessionUnavailableCopy(backend));
      setPhase('error');
      return;
    }
    if (auth !== undefined && auth !== null) {
      let hasSession: boolean;
      try {
        hasSession = await auth.hasCloudSession();
      } catch {
        // A probe that cannot settle (session refresh transport failed) must
        // stay retryable instead of stranding the page on Loading forever.
        setSnapshot(null);
        setError(desktopBackendServiceCopy);
        setPhase('error');
        return;
      }
      if (!hasSession) {
        setSnapshot(null);
        setError(desktopBackendUnauthorizedCopy);
        setPhase('signed-out');
        return;
      }
    }
    setPhase(current => (current === 'ready' ? current : 'loading'));
    try {
      const next = await loadConnectors(backend);
      setSnapshot(next);
      setError(null);
      setPhase('ready');
    } catch (reason) {
      setSnapshot(null);
      setError(desktopReadErrorCopy(reason));
      setPhase('error');
    }
  }, []);

  useEffect(() => {
    reload().catch(() => undefined);
  }, [reload]);

  const sections = useMemo(() => {
    if (snapshot === null) {
      return [];
    }
    return [
      {
        empty: 'No apps were returned by the catalogue.',
        items: exploreApps(snapshot),
        key: 'Explore',
        title: 'Explore',
      },
      {
        empty:
          snapshot.enabledError === null
            ? 'No installed apps.'
            : snapshot.enabledError,
        items: installedApps(snapshot),
        key: 'Installed',
        title: 'Installed',
      },
      {
        empty:
          snapshot.ownerUid === null
            ? 'Owned apps are unavailable until the account profile loads.'
            : 'No apps owned by this account.',
        items: myApps(snapshot, snapshot.ownerUid),
        key: 'My Apps',
        title: 'My Apps',
      },
      {
        empty: 'No apps with an external service connection were returned.',
        items: serviceApps(snapshot),
        key: 'Services',
        title: 'Services',
      },
    ];
  }, [snapshot]);

  const setEnabled = async (app: CloudApp, enabled: boolean) => {
    const backend = omiBackend;
    if (backend === undefined || backend === null || pendingId !== null) {
      return;
    }
    setPendingId(app.id);
    setActionError(null);
    try {
      if (enabled) {
        await enableCloudApp(backend, app.id);
      } else {
        await disableCloudApp(backend, app.id);
      }
      await reload();
    } catch (reason) {
      setActionError(desktopReadErrorCopy(reason));
    } finally {
      setPendingId(null);
    }
  };

  const signIn = async () => {
    if (onSignIn === undefined) {
      return;
    }
    await onSignIn();
    await reload();
  };

  return (
    <ScrollView
      contentContainerStyle={[styles.destinationPage, catalogStyles.page]}>
      <View accessibilityRole="tablist" style={catalogStyles.tabs}>
        {catalogTabs.map(tab => (
          <FocusPressable
            key={tab}
            accessibilityRole="tab"
            accessibilityLabel={tab === 'My Apps' ? 'My apps' : `${tab} apps`}
            accessibilityState={{selected: catalogTab === tab}}
            onPress={() => setCatalogTab(tab)}
            style={[
              catalogStyles.tab,
              catalogTab === tab && catalogStyles.tabSelected,
            ]}>
            <Text
              style={[
                catalogStyles.tabText,
                catalogTab === tab && catalogStyles.tabTextSelected,
              ]}>
              {tab}
            </Text>
          </FocusPressable>
        ))}
      </View>
      <View style={[styles.destinationSections, styles.cloudSections]}>
        {phase === 'loading' && snapshot === null ? (
          <View style={[styles.destinationSection, catalogStyles.state]}>
            <ActivityIndicator color="#888888" />
            <Text style={styles.projectionEmptyCopy}>Loading apps…</Text>
          </View>
        ) : phase === 'signed-out' || phase === 'error' ? (
          <View style={[styles.destinationSection, catalogStyles.state]}>
            <Puzzle color={mobileColor.textMuted} size={28} />
            <Text style={styles.destinationSectionTitle}>
              {phase === 'signed-out' ? 'Signed out' : 'Apps unavailable'}
            </Text>
            <Text style={styles.projectionEmptyCopy}>
              {error ?? desktopBackendUnauthorizedCopy}
            </Text>
            {phase === 'signed-out' && onSignIn !== undefined && (
              <FocusPressable
                accessibilityLabel="Sign in"
                accessibilityRole="button"
                disabled={signingIn}
                onPress={() => {
                  signIn().catch(() => undefined);
                }}
                style={({pressed}) => [
                  styles.cloudAction,
                  catalogStyles.touchAction,
                  pressed && styles.pressed,
                ]}>
                <Text style={styles.cloudActionText}>
                  {signingIn ? 'Signing in…' : 'Sign in'}
                </Text>
              </FocusPressable>
            )}
            {phase === 'error' &&
              Platform.OS !== 'web' &&
              error !== desktopBackendConfigurationCopy && (
                <FocusPressable
                  accessibilityLabel="Retry apps"
                  accessibilityRole="button"
                  onPress={() => {
                    reload().catch(() => undefined);
                  }}
                  style={({pressed}) => [
                    styles.cloudAction,
                    catalogStyles.touchAction,
                    pressed && styles.pressed,
                  ]}>
                  <Text style={styles.cloudActionText}>Retry</Text>
                </FocusPressable>
              )}
          </View>
        ) : (
          sections
            .filter(section => section.key === catalogTab)
            .map(section => (
              <View key={section.key} style={catalogStyles.section}>
                <Text style={styles.destinationSectionTitle}>
                  {section.title}
                </Text>
                {section.items.length === 0 ? (
                  <Text style={styles.projectionEmptyCopy}>
                    {section.empty}
                  </Text>
                ) : (
                  section.items.map(app => (
                    <View
                      key={`${section.key}-${app.id}`}
                      style={catalogStyles.card}>
                      <View style={catalogStyles.appIcon}>
                        <Puzzle color={mobileColor.text} size={24} />
                      </View>
                      <View style={styles.cloudRowBody}>
                        <Text style={styles.cloudRowTitle}>{app.name}</Text>
                        {app.description.length > 0 && (
                          <Text numberOfLines={2} style={styles.cloudRowMeta}>
                            {app.description}
                          </Text>
                        )}
                        <Text style={styles.cloudRowMeta}>
                          {[
                            app.category.length > 0 ? app.category : null,
                            app.author.length > 0 ? app.author : null,
                            app.enabled ? 'Installed' : 'Not installed',
                          ]
                            .filter(item => item !== null)
                            .join(' · ')}
                        </Text>
                      </View>
                      <FocusPressable
                        accessibilityLabel={
                          app.enabled
                            ? `Remove ${app.name}`
                            : `Install ${app.name}`
                        }
                        accessibilityRole="button"
                        disabled={pendingId !== null}
                        onPress={() => {
                          setEnabled(app, !app.enabled).catch(() => undefined);
                        }}
                        style={({pressed}) => [
                          styles.cloudAction,
                          catalogStyles.install,
                          pressed && styles.pressed,
                        ]}>
                        <Text style={styles.cloudActionText}>
                          {pendingId === app.id
                            ? app.enabled
                              ? 'Removing…'
                              : 'Installing…'
                            : app.enabled
                            ? 'Remove'
                            : 'Install'}
                        </Text>
                      </FocusPressable>
                    </View>
                  ))
                )}
              </View>
            ))
        )}
        {actionError !== null && (
          <Text accessibilityRole="alert" style={styles.cloudActionError}>
            {actionError}
          </Text>
        )}
      </View>
    </ScrollView>
  );
}

const catalogStyles = StyleSheet.create({
  page: {paddingHorizontal: 16, paddingTop: 4, paddingBottom: 24, gap: 20},
  tabs: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  tab: {
    flexBasis: '45%',
    flexGrow: 1,
    minHeight: 44,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: mobileColor.surface,
  },
  tabSelected: {backgroundColor: mobileColor.text},
  tabText: {fontSize: 13, fontWeight: '600', color: mobileColor.textMuted},
  tabTextSelected: {color: mobileColor.background},
  section: {gap: 12},
  state: {
    borderRadius: 22,
    padding: 24,
    gap: 12,
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderColor: mobileColor.border,
  },
  card: {
    backgroundColor: mobileColor.surface,
    borderColor: mobileColor.border,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 22,
    padding: 20,
    gap: 12,
  },
  appIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
    backgroundColor: mobileColor.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  install: {minHeight: 44, alignSelf: 'stretch', marginTop: 0},
  touchAction: {minHeight: 44},
});
