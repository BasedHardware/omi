import * as React from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { rotateImage } from '../modules/imaging';
import { toBase64Image } from '../utils/base64';
import { Agent } from '../agent/Agent';
import { InvalidateSync } from '../utils/invalidateSync';
import { textToSpeech } from '../modules/openai';

function usePhotos(device: BluetoothRemoteGATTServer) {

    // Subscribe to device
    const [photos, setPhotos] = React.useState<Array<{ data: Uint8Array; timestamp: number }>>([]);
    const [subscribed, setSubscribed] = React.useState<boolean>(false);
    React.useEffect(() => {
        (async () => {

            // Get firmware version
            let firmwareVersion = '0.0.0'; // Default to old
            try {
                const deviceInfoService = await device.getPrimaryService('device_information');
                const firmwareChar = await deviceInfoService.getCharacteristic('firmware_revision_string');
                const firmwareValue = await firmwareChar.readValue();
                firmwareVersion = new TextDecoder().decode(firmwareValue);
            } catch (e) {
                console.error('Failed to read firmware version', e);
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

            const newRotationLogic = compareVersions(firmwareVersion, '2.1.1') >= 0;

            let previousChunk = -1;
            let buffer: Uint8Array = new Uint8Array(0);
            let orientation: number = 0;
            function onChunk(id: number | null, data: Uint8Array) {

                // Resolve if packet is the first one
                if (previousChunk === -1) {
                    if (id === null) {
                        return;
                    } else if (id === 0) {
                        previousChunk = 0;
                        buffer = new Uint8Array(0);
                        if (newRotationLogic) {
                            orientation = data[0];
                            data = data.slice(1);
                        }
                    } else {
                        return;
                    }
                } else {
                    if (id === null) {
                        console.log('Photo received', buffer);
                        const timestamp = Date.now(); // Get current timestamp
                        let rotation: '0' | '90' | '180' | '270' = '180';
                        if (newRotationLogic) {
                            rotation = '0';
                            if (orientation === 1) {
                                rotation = '90';
                            } else if (orientation === 2) {
                                rotation = '180';
                            } else if (orientation === 3) {
                                rotation = '270';
                            }
                        }
                        rotateImage(buffer, rotation).then((rotated) => {
                            console.log('Rotated photo', rotated);
                            setPhotos((p) => [...p, { data: rotated, timestamp: timestamp }]); // Store data and timestamp
                        });
                        previousChunk = -1;
                        return;
                    } else {
                        if (id !== previousChunk + 1) {
                            previousChunk = -1;
                            console.error('Invalid chunk', id, previousChunk);
                            return;
                        }
                        previousChunk = id;
                    }
                }

                // Append data
                buffer = new Uint8Array([...buffer, ...data]);
            }

            // Subscribe for photo updates
            const service = await device.getPrimaryService('19B10000-E8F2-537E-4F6C-D104768A1214'.toLowerCase());
            const photoCharacteristic = await service.getCharacteristic('19b10005-e8f2-537e-4f6c-d104768a1214');
            await photoCharacteristic.startNotifications();
            setSubscribed(true);
            photoCharacteristic.addEventListener('characteristicvaluechanged', (e) => {
                let value = (e.target as BluetoothRemoteGATTCharacteristic).value!;
                let array = new Uint8Array(value.buffer);
                if (array[0] == 0xff && array[1] == 0xff) {
                    onChunk(null, new Uint8Array());
                } else {
                    let packetId = array[0] + (array[1] << 8);
                    let packet = array.slice(2);
                    onChunk(packetId, packet);
                }
            });
            // Start automatic photo capture every 5s
            const photoControlCharacteristic = await service.getCharacteristic('19b10006-e8f2-537e-4f6c-d104768a1214');
            await photoControlCharacteristic.writeValue(new Uint8Array([0x05]));
        })();
    }, []);

    return [subscribed, photos] as const;
}

export const DeviceView = React.memo((props: { device: BluetoothRemoteGATTServer }) => {
    const [subscribed, photos] = usePhotos(props.device);
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
    React.useEffect(() => {
        processedPhotos.current = photos.map(p => p.data);
        sync.invalidate();
    }, [photos]);

    return (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            {/* Display photos in a grid filling the screen */}
            <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: '#111' }}>
                <ScrollView contentContainerStyle={{ flexDirection: 'row', flexWrap: 'wrap', padding: 5 }}>
                    {photos.slice().reverse().map((photo, index) => ( // Display newest first
                        <Pressable
                            key={photos.length - 1 - index} // Use original index for key stability if needed
                            onPressIn={() => setActivePhotoIndex(photos.length - 1 - index)}
                            onPressOut={() => setActivePhotoIndex(null)}
                            style={{
                                position: 'relative',
                                width: '33%', // Roughly 3 images per row
                                aspectRatio: 1, // Make images square
                                padding: 2 // Add spacing
                            }}
                        >
                            <Image style={{ width: '100%', height: '100%', borderRadius: 5 }} source={{ uri: toBase64Image(photo.data) }} />
                            {activePhotoIndex === (photos.length - 1 - index) && (
                                <View style={{
                                    position: 'absolute',
                                    bottom: 2, // Adjusted for padding
                                    left: 2,
                                    right: 2,
                                    backgroundColor: 'rgba(0, 0, 0, 0.7)',
                                    paddingVertical: 3,
                                    paddingHorizontal: 5,
                                    alignItems: 'center',
                                    borderRadius: 3
                                }}>
                                    <Text style={{ color: 'white', fontSize: 10 }}>
                                        {new Date(photo.timestamp).toLocaleTimeString()}
                                    </Text>
                                </View>
                            )}
                        </Pressable>
                    ))}
                </ScrollView>
            </View>
        </View>
    );
});
