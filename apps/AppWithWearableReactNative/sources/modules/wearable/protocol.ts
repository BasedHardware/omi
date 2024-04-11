import { BTCharacteristic, BTDevice } from "./bt_common";

export const SUPER_SERVICE = '19b10000-e8f2-537e-4f6c-d104768a1214';
export const COMPASS_SERVICE = '4fafc201-1fb5-459e-8fcc-c5c9c331914b';
export const KNOWN_BT_SERVICES = [SUPER_SERVICE, COMPASS_SERVICE];

export type CodecType = 'pcm-16' | 'pcm-8' | 'mulaw-16' | 'mulaw-8' | 'opus';

export type ProtocolDefinition = {
    kind: 'super' | 'compass',
    codec: CodecType,
    source: BTCharacteristic
}

export function supportedDeviceNames(name: string) {
    if (['super', 'friend'].indexOf(name.toLowerCase()) >= 0) {
        return true;
    }
    if (name.toLowerCase().startsWith('compass')) {
        return true;
    }
    return false;
}


async function resolveSuperProtocol(device: BTDevice): Promise<ProtocolDefinition | null> {

    // Search for service
    let superService = device.services.find((v) => v.id === '19b10000-e8f2-537e-4f6c-d104768a1214')
    if (!superService) {
        return null;
    }

    // Search for audio characteristic
    let audioCharacteristic = superService.characteristics.find((v) => v.id === '19b10001-e8f2-537e-4f6c-d104768a1214');
    if (!audioCharacteristic) {
        return null;
    }

    // Search for codec characteristic
    let codecCharacteristic = superService.characteristics.find((v) => v.id === '19b10002-e8f2-537e-4f6c-d104768a1214');
    if (!codecCharacteristic) {
        return null;
    }
    let value = await codecCharacteristic.read();
    if (value.length < 1) {
        return null;
    }
    let codec: CodecType;
    let codecId = value[0];
    if (codecId === 0) {
        codec = 'pcm-16';
    } else if (codecId === 1) {
        codec = 'pcm-8';
    } else if (codecId === 10) {
        codec = 'mulaw-16'
    } else if (codecId === 11) {
        codec = 'mulaw-8'
    } else if (codecId === 20) {
        codec = 'opus'
    } else {
        console.warn('Unknown codec: ' + codecId);
        return null;
    }

    return {
        kind: 'super',
        codec,
        source: audioCharacteristic
    };
}

async function resolveCompasProtocol(device: BTDevice): Promise<ProtocolDefinition | null> {

    // Search for service
    let service = device.services.find((v) => v.id === '4fafc201-1fb5-459e-8fcc-c5c9c331914b')
    if (!service) {
        return null;
    }

    // Search for characteristic
    let audioCharacteristic = service.characteristics.find((v) => v.id === 'beb5483e-36e1-4688-b7f5-ea07361b26a8');
    if (!audioCharacteristic) {
        return null;
    }

    // Check that other characteristics are present since service id is from a sample code
    if (!service.characteristics.find((v) => v.id === '00002bed-0000-1000-8000-00805f9b34fb')) { // This one is battery level characteristic
        return null;
    }
    if (!service.characteristics.find((v) => v.id === '9f83442c-7da2-49ca-94e3-b06201a58508')) { // This one is not googlable
        return null;
    }

    return {
        kind: 'compass',
        codec: 'pcm-8' as const,
        source: audioCharacteristic
    };
}

export async function resolveProtocol(device: BTDevice): Promise<ProtocolDefinition | null> {

    let found = await resolveSuperProtocol(device);
    if (found) {
        return found;
    }

    found = await resolveCompasProtocol(device);
    if (found) {
        return found;
    }

    return null;
}

export function startPacketizer() {

    // Buffers
    let last: { p: number, f: number } | null = null;
    let frames: Uint8Array[] = [];
    let pending: Uint8Array = new Uint8Array();
    let lost = 0;

    // Return object
    return {
        add: (data: Uint8Array) => {

            // Parse packet
            let index = (data[0]) + (data[1] << 8);
            let internal = data[2];
            let content = data.subarray(3);
            console.log('Received: ' + index + ' (' + internal + ') - ' + content.length + ' bytes');

            // Start of a new frame
            if (!last && internal === 0) {
                last = { p: index, f: internal };
                pending = content;
                return;
            }

            // Not started yet
            if (!last) {
                return;
            }

            // Lost frame - reset state
            if (index !== last.p + 1 || (internal !== 0 && internal !== last.f + 1)) {
                console.warn('Lost frame');
                last = null;
                pending = new Uint8Array();
                lost += 1;
                return;
            }

            // Start of a new frame
            if (internal === 0) {// Start of a new frame
                frames.push(pending); // Save frame
                pending = content; // Start new frame
                last.f = internal; // Update internal frame id
                last.p++; // Update packet id
                return;
            }

            // Continue frame
            pending = new Uint8Array([...pending, ...content]);
            last.f = internal; // Update internal frame id
            last.p++; // Update packet id
        },
        build: () => {
            if (pending.length > 0) {
                frames.push(pending);
            }
            return { frames, lost };
        }
    };
}