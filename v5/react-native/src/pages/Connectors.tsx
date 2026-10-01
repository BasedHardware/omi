import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {Platform, ScrollView, Text, View} from 'react-native';
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
import {MaterialIcon} from '../ui/MaterialIcon';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {OmiButton, OmiChip, OmiPageState} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';
import {MobileGroup, MobileInlineState, MobileRow} from '../mobile/MobileList';

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
  const theme = useOmiTheme();
  const local = useOmiStyles(createStyles);
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
    <ScrollView contentContainerStyle={local.page}>
      <ScrollView
        horizontal
        accessibilityLabel="App catalogue"
        accessibilityRole="tablist"
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={local.chips}
        style={local.chipRail}>
        {catalogTabs.map(tab => (
          <OmiChip
            key={tab}
            label={tab}
            selected={catalogTab === tab}
            onPress={() => setCatalogTab(tab)}
          />
        ))}
      </ScrollView>
      {phase === 'loading' && snapshot === null ? (
        <OmiPageState kind="loading" label="Loading apps…" />
      ) : phase === 'signed-out' ? (
        <View style={local.state}>
          <OmiPageState
            kind="empty"
            icon="extension"
            title="Signed Out"
            message={error ?? desktopBackendUnauthorizedCopy}
          />
          {onSignIn !== undefined && (
            <OmiButton
              busy={signingIn}
              label="Sign In"
              variant="primary"
              onPress={() => {
                signIn().catch(() => undefined);
              }}
            />
          )}
        </View>
      ) : phase === 'error' ? (
        <View accessibilityRole="alert">
          <OmiPageState
            kind="error"
            title={
              Platform.OS === 'web' ? 'Apps Unavailable' : 'Couldn’t Load Apps'
            }
            message={error ?? undefined}
            onRetry={
              Platform.OS !== 'web' && error !== desktopBackendConfigurationCopy
                ? () => {
                    reload().catch(() => undefined);
                  }
                : undefined
            }
          />
        </View>
      ) : (
        sections
          .filter(section => section.key === catalogTab)
          .map(section => (
            <MobileGroup key={section.key} inset={68}>
              {section.items.length === 0 ? (
                <MobileInlineState label={section.empty} />
              ) : (
                section.items.map(app => (
                  <MobileRow
                    key={`${section.key}-${app.id}`}
                    leading={
                      <View style={local.appIcon}>
                        <MaterialIcon
                          name="extension"
                          color={theme.color.inkSecondary}
                          size={theme.size.iconSmall}
                        />
                      </View>
                    }
                    title={app.name}
                    subtitle={
                      app.description.length > 0 ? app.description : null
                    }
                    meta={[
                      app.category.length > 0 ? app.category : null,
                      app.author.length > 0 ? app.author : null,
                      app.enabled ? 'Installed' : 'Not installed',
                    ]
                      .filter(item => item !== null)
                      .join(' · ')}
                    trailing={
                      <View style={local.rowAction}>
                        <OmiButton
                          accessibilityLabel={
                            app.enabled
                              ? `Remove ${app.name}`
                              : `Install ${app.name}`
                          }
                          busy={pendingId === app.id}
                          compact
                          disabled={pendingId !== null}
                          label={app.enabled ? 'Remove' : 'Install'}
                          onPress={() => {
                            setEnabled(app, !app.enabled).catch(
                              () => undefined,
                            );
                          }}
                        />
                      </View>
                    }
                  />
                ))
              )}
            </MobileGroup>
          ))
      )}
      {actionError !== null && (
        <Text accessibilityRole="alert" style={local.actionError}>
          {actionError}
        </Text>
      )}
    </ScrollView>
  );
}

const createStyles = (t: OmiTheme) => ({
  page: {
    gap: t.space.lg,
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingTop: t.space.xs,
    paddingBottom: t.space.xxl,
  },
  chipRail: {
    flexGrow: 0,
    marginHorizontal: -t.layout.pageGutter.mobile,
  },
  chips: {
    gap: t.space.sm,
    paddingHorizontal: t.layout.pageGutter.mobile,
  },
  state: {alignItems: 'center' as const, gap: t.space.md},
  appIcon: {
    width: t.size.controlCompact,
    height: t.size.controlCompact,
    borderRadius: t.radius.row - 2,
    backgroundColor: t.color.fill,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  rowAction: {paddingRight: t.space.sm},
  actionError: {
    ...t.type.subhead,
    color: t.color.danger,
    paddingHorizontal: t.space.xs,
  },
});
