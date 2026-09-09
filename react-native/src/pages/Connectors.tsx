import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
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
  cloudErrorCanRetry,
  cloudSessionUnavailableCopy,
  type CloudApp,
  type ConnectorsSnapshot,
} from '../desktopCloudClient';
import {
  desktopBackendConfigurationCopy,
  desktopBackendServiceCopy,
  desktopBackendUnauthorizedCopy,
  desktopReadErrorCopy,
  appCategoryCopy,
  appDisplayName,
  appRatingCopy,
  visibleDisplayText,
} from '../desktopReadClient';
import {omiAuth, omiBackend} from '../omiNative';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';

function appRowMeta(app: CloudApp, installKnown: boolean): string {
  const category = appCategoryCopy(app.category);
  const author = visibleDisplayText(app.author);
  return [
    category !== '' ? category : null,
    author !== '' ? author : null,
    app.private ? 'Private' : null,
    appRatingCopy(app.ratingAvg, app.ratingCount),
    app.connectedAccounts.length > 0
      ? 'Connected'
      : installKnown
      ? app.enabled
        ? 'Installed'
        : 'Not installed'
      : null,
  ]
    .filter(item => item !== null)
    .join(' · ');
}

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
  const [appsCanRetry, setAppsCanRetry] = useState(true);
  const [snapshot, setSnapshot] = useState<ConnectorsSnapshot | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [writesAvailable, setWritesAvailable] = useState(true);

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
        setAppsCanRetry(true);
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
      setAppsCanRetry(true);
      setPhase('ready');
    } catch (reason) {
      setSnapshot(null);
      setError(desktopReadErrorCopy(reason));
      setAppsCanRetry(cloudErrorCanRetry(reason));
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
            ? snapshot.ownerError ?? 'Owned apps are unavailable.'
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
      if (!cloudErrorCanRetry(reason)) {
        setWritesAvailable(false);
      }
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

  const installKnown = snapshot !== null && snapshot.enabledIds !== null;

  return (
    <ScrollView contentContainerStyle={styles.destinationPage}>
      <View style={[styles.destinationSections, styles.cloudSections]}>
        {phase === 'loading' && snapshot === null ? (
          <View style={styles.destinationSection}>
            <ActivityIndicator color="#888888" />
            <Text style={styles.projectionEmptyCopy}>Loading apps…</Text>
          </View>
        ) : phase === 'signed-out' || phase === 'error' ? (
          <View style={styles.destinationSection}>
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
                  pressed && styles.pressed,
                ]}>
                <Text style={styles.cloudActionText}>
                  {signingIn ? 'Signing in…' : 'Sign in'}
                </Text>
              </FocusPressable>
            )}
            {phase === 'error' &&
              Platform.OS !== 'web' &&
              error !== desktopBackendConfigurationCopy &&
              appsCanRetry && (
                <FocusPressable
                  accessibilityLabel="Retry apps"
                  accessibilityRole="button"
                  onPress={() => {
                    reload().catch(() => undefined);
                  }}
                  style={({pressed}) => [
                    styles.cloudAction,
                    pressed && styles.pressed,
                  ]}>
                  <Text style={styles.cloudActionText}>Retry</Text>
                </FocusPressable>
              )}
          </View>
        ) : (
          sections.map(section => (
            <View key={section.key} style={styles.destinationSection}>
              <Text style={styles.destinationSectionTitle}>
                {section.title}
              </Text>
              {section.items.length === 0 ? (
                <Text style={styles.projectionEmptyCopy}>{section.empty}</Text>
              ) : (
                section.items.map(app => {
                  const meta = appRowMeta(app, installKnown);
                  const name = appDisplayName(app.name);
                  const description = visibleDisplayText(app.description);
                  return (
                    <View
                      key={`${section.key}-${app.id}`}
                      style={styles.cloudRow}>
                      <View style={styles.cloudRowBody}>
                        <Text style={styles.cloudRowTitle}>{name}</Text>
                        {description !== '' && (
                          <Text numberOfLines={2} style={styles.cloudRowMeta}>
                            {description}
                          </Text>
                        )}
                        {meta.length > 0 && (
                          <Text style={styles.cloudRowMeta}>{meta}</Text>
                        )}
                      </View>
                      {writesAvailable && installKnown && (
                        <FocusPressable
                          accessibilityLabel={
                            app.enabled ? `Remove ${name}` : `Install ${name}`
                          }
                          accessibilityRole="button"
                          disabled={pendingId !== null}
                          onPress={() => {
                            setEnabled(app, !app.enabled).catch(
                              () => undefined,
                            );
                          }}
                          style={({pressed}) => [
                            styles.cloudAction,
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
                      )}
                    </View>
                  );
                })
              )}
            </View>
          ))
        )}
        {actionError !== null && (
          <Text style={styles.cloudActionError}>{actionError}</Text>
        )}
      </View>
    </ScrollView>
  );
}
