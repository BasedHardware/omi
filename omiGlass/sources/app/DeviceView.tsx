import * as React from 'react';
import { ActivityIndicator, Image, Pressable, Text, TextInput, View } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { rotateImage } from '../modules/imaging';
import { toBase64Image } from '../utils/base64';
import { Agent } from '../agent/Agent';
import { InvalidateSync } from '../utils/invalidateSync';
import { stopAudio } from '../modules/openai';
import { useBleCharacteristic } from '../utils/useBleCharacteristic';
import { useBatteryLevel } from '../utils/useBatteryLevel';

// BLE UUIDs for the OMI Glass
const OMI_SERVICE = '19b10000-e8f2-537e-4f6c-d104768a1214';
const PHOTO_CHAR = '19b10005-e8f2-537e-4f6c-d104768a1214';
const PHOTO_CONTROL_CHAR = '19b10006-e8f2-537e-4f6c-d104768a1214';

function usePhotos(device: BluetoothRemoteGATTServer) {
    const MAX_PHOTOS = 100;
    const [photos, setPhotos] = React.useState<Array<{ data: Uint8Array; timestamp: number }>>([]);
    const newRotationRef = React.useRef(false);

    // Chunk reassembly state (refs to avoid stale closures)
    const chunkState = React.useRef({
        previousChunk: -1,
        buffer: new Uint8Array(0),
        orientation: 0,
    });

    // Resolve firmware version once on mount to determine rotation logic
    React.useEffect(() => {
        (async () => {
            try {
                const deviceInfoService = await device.getPrimaryService('device_information');
                const firmwareChar = await deviceInfoService.getCharacteristic('firmware_revision_string');
                const firmwareValue = await firmwareChar.readValue();
                const firmwareVersion = new TextDecoder().decode(firmwareValue);
                // Rotation logic changed in firmware 2.1.1+
                newRotationRef.current = compareVersions(firmwareVersion, '2.1.1') >= 0;
            } catch (e) {
                console.error('Failed to read firmware version', e);
            }
        })();
    }, [device]);

    // NOTE: onChunk is a hoisted function declaration using only refs (chunkState, newRotationRef),
    // so this callback is safe with [] deps. If onChunk ever reads React state, add it to deps.
    const onPhotoNotification = React.useCallback((e: Event) => {
        const value = (e.target as BluetoothRemoteGATTCharacteristic).value!;
        const array = new Uint8Array(value.buffer);
        if (array[0] === 0xff && array[1] === 0xff) {
            onChunk(null, new Uint8Array());
        } else {
            const packetId = array[0] + (array[1] << 8);
            onChunk(packetId, array.slice(2));
        }
    }, []); // onChunk is defined below via closure — refs keep it stable

    // Subscribe to photo data notifications via reusable hook
    const { subscribed } = useBleCharacteristic(device, {
        serviceUUID: OMI_SERVICE,
        characteristicUUID: PHOTO_CHAR,
        onCharacteristicChanged: onPhotoNotification,
    });

    // Start automatic photo capture on mount, stop on unmount
    React.useEffect(() => {
        let cancelled = false;
        let controlChar: BluetoothRemoteGATTCharacteristic | null = null;

        (async () => {
            try {
                const service = await device.getPrimaryService(OMI_SERVICE);
                if (cancelled) return;
                controlChar = await service.getCharacteristic(PHOTO_CONTROL_CHAR);
                if (cancelled) return;
                await controlChar.writeValue(new Uint8Array([0x05]));
            } catch (err) {
                console.error('Failed to start photo capture:', err);
            }
        })();

        return () => {
            cancelled = true;
            if (controlChar) {
                controlChar.writeValue(new Uint8Array([0x00])).catch(() => {});
            }
        };
    }, [device]);

    // Chunk reassembly + photo processing (uses refs to stay stable across renders)
    function onChunk(id: number | null, data: Uint8Array) {
        const s = chunkState.current;
        if (s.previousChunk === -1) {
            if (id === null) return;
            if (id === 0) {
                s.previousChunk = 0;
                s.buffer = new Uint8Array(0);
                if (newRotationRef.current) {
                    s.orientation = data[0];
                    data = data.slice(1);
                }
            } else {
                return;
            }
        } else {
            if (id === null) {
                console.log('Photo received', s.buffer);
                const timestamp = Date.now();
                let rotation: '0' | '90' | '180' | '270' = '180';
                if (newRotationRef.current) {
                    rotation = (['0', '90', '180', '270'][s.orientation] ?? '180') as '0' | '90' | '180' | '270';
                }
                rotateImage(s.buffer, rotation).then((rotated) => {
                    console.log('Rotated photo', rotated);
                    setPhotos((p) => {
                        const next = [...p, { data: rotated, timestamp }];
                        return next.length > MAX_PHOTOS ? next.slice(next.length - MAX_PHOTOS) : next;
                    });
                });
                s.previousChunk = -1;
                return;
            } else {
                if (id !== s.previousChunk + 1) {
                    s.previousChunk = -1;
                    console.error('Invalid chunk', id, s.previousChunk);
                    return;
                }
                s.previousChunk = id;
            }
        }
        s.buffer = new Uint8Array([...s.buffer, ...data]);
    }

    return [subscribed, photos] as const;
}

function compareVersions(v1: string, v2: string): number {
    const parts1 = v1.split('.').map(Number);
    const parts2 = v2.split('.').map(Number);
    const len = Math.max(parts1.length, parts2.length);
    for (let i = 0; i < len; i++) {
        const p1 = parts1[i] || 0;
        const p2 = parts2[i] || 0;
        if (p1 > p2) return 1;
        if (p1 < p2) return -1;
    }
    return 0;
}

export const DeviceView = React.memo((props: { device: BluetoothRemoteGATTServer }) => {
    const [subscribed, photos] = usePhotos(props.device);
    const { level: batteryLevel } = useBatteryLevel(props.device);
    const agent = React.useMemo(() => new Agent(), []);
    const agentState = agent.use();
    const [activePhotoIndex, setActivePhotoIndex] = React.useState<number | null>(null);

    // Background processing agent
    const processedPhotos = React.useRef<Uint8Array[]>([]);
    const sync = React.useMemo(() => {
        let processed = 0;
        return new InvalidateSync(async () => {
            if (processedPhotos.current.length > processed) {
                let unprocessed = processedPhotos.current.slice(processed);
                processed = processedPhotos.current.length;
                await agent.addPhoto(unprocessed);
            }
        });
    }, []);

    // Stop InvalidateSync and AudioContext on unmount to prevent pending callbacks
    React.useEffect(() => {
        return () => {
            sync.stop();
            stopAudio();
        };
    }, [sync]);

    React.useEffect(() => {
        processedPhotos.current = photos.map(p => p.data);
        sync.invalidate();
    }, [photos]);

    // Pre-reverse photos for newest-first display
    const reversedPhotos = React.useMemo(() => [...photos].reverse(), [photos]);

    const renderItem = React.useCallback(({ item, index }: { item: typeof photos[number]; index: number }) => {
        const originalIndex = photos.length - 1 - index;
        return (
            <Pressable
                onPressIn={() => setActivePhotoIndex(originalIndex)}
                onPressOut={() => setActivePhotoIndex(null)}
                style={{
                    position: 'relative',
                    flex: 1 / 3, // 3 images per row
                    aspectRatio: 1, // Square thumbnails
                    padding: 2,
                }}
            >
                <Image style={{ width: '100%', height: '100%', borderRadius: 5 }} source={{ uri: toBase64Image(item.data) }} />
                {activePhotoIndex === originalIndex && (
                    <View style={{
                        position: 'absolute',
                        bottom: 2,
                        left: 2,
                        right: 2,
                        backgroundColor: 'rgba(0, 0, 0, 0.7)',
                        paddingVertical: 3,
                        paddingHorizontal: 5,
                        alignItems: 'center',
                        borderRadius: 3,
                    }}>
                        <Text style={{ color: 'white', fontSize: 10 }}>
                            {new Date(item.timestamp).toLocaleTimeString()}
                        </Text>
                    </View>
                )}
            </Pressable>
        );
    }, [photos.length, activePhotoIndex]);

    const keyExtractor = React.useCallback((item: typeof photos[number]) => String(item.timestamp), []);

    return (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            {/* Display photos in a virtualized grid filling the screen */}
            <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: '#111' }}>                    <FlashList
                    data={reversedPhotos}
                    renderItem={renderItem}
                    keyExtractor={keyExtractor}
                    numColumns={3}
                    estimatedItemSize={120}
                    contentContainerStyle={{ padding: 5 }}
                    ListHeaderComponent={batteryLevel >= 0 ? (
                        <View style={{ padding: 6, alignItems: 'center' }}>
                            <Text style={{ color: batteryLevel > 20 ? '#4CD964' : '#FF3B30', fontSize: 12, fontWeight: '600' }}>
                                Battery: {batteryLevel}%
                            </Text>
                        </View>
                    ) : null}
                />
            </View>
        </View>
    );
});
