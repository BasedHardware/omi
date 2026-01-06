'use client';

import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, ZoomControl } from 'react-leaflet';
import L from 'leaflet';
import { ExternalLink } from 'lucide-react';
import 'leaflet/dist/leaflet.css';

// Create simple purple marker icon
function createMarkerIcon() {
  return L.divIcon({
    className: 'custom-marker',
    html: `<div style="
      width: 24px;
      height: 24px;
      background: #8B5CF6;
      border: 2px solid white;
      border-radius: 50%;
      box-shadow: 0 2px 8px rgba(139, 92, 246, 0.4);
    "></div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  });
}

interface SingleLocationMapProps {
  latitude: number;
  longitude: number;
  address?: string | null;
  height?: number | string;
  className?: string;
}

// Component to set view and handle container resize
function SetView({ latitude, longitude }: { latitude: number; longitude: number }) {
  const map = useMap();
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;

    // Stop any ongoing animations before setting view
    map.stop();
    map.setView([latitude, longitude], 15, { animate: false });

    // Small delay to ensure container is properly sized
    const timeout = setTimeout(() => {
      if (isMountedRef.current) {
        map.invalidateSize();
      }
    }, 100);

    return () => {
      isMountedRef.current = false;
      clearTimeout(timeout);
      // Stop animations on unmount to prevent errors
      try {
        map.stop();
      } catch {
        // Ignore - map already disposed
      }
    };
  }, [map, latitude, longitude]);

  return null;
}

export default function SingleLocationMap({
  latitude,
  longitude,
  address,
  height = 280,
  className,
}: SingleLocationMapProps) {
  const openStreetMapUrl = `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=15/${latitude}/${longitude}`;

  return (
    <div
      className={className}
      style={{ height: typeof height === 'number' ? `${height}px` : height, width: '100%' }}
    >
      <MapContainer
        center={[latitude, longitude]}
        zoom={15}
        style={{ height: '100%', width: '100%' }}
        scrollWheelZoom={false}
        zoomControl={false}
        className="z-0 [&_.leaflet-control-zoom]:!border-none [&_.leaflet-control-zoom]:!rounded-lg [&_.leaflet-control-zoom]:!bg-bg-tertiary/80 [&_.leaflet-control-zoom]:!backdrop-blur-sm [&_.leaflet-control-zoom-in]:!text-text-secondary [&_.leaflet-control-zoom-in]:!bg-transparent [&_.leaflet-control-zoom-in]:!border-none [&_.leaflet-control-zoom-in]:!w-8 [&_.leaflet-control-zoom-in]:!h-8 [&_.leaflet-control-zoom-in]:!leading-8 [&_.leaflet-control-zoom-out]:!text-text-secondary [&_.leaflet-control-zoom-out]:!bg-transparent [&_.leaflet-control-zoom-out]:!border-none [&_.leaflet-control-zoom-out]:!w-8 [&_.leaflet-control-zoom-out]:!h-8 [&_.leaflet-control-zoom-out]:!leading-8 hover:[&_.leaflet-control-zoom-in]:!text-text-primary hover:[&_.leaflet-control-zoom-out]:!text-text-primary"
      >
        <ZoomControl position="bottomright" />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        <SetView latitude={latitude} longitude={longitude} />
        <Marker position={[latitude, longitude]} icon={createMarkerIcon()}>
          <Popup className="dark-popup">
            <div className="text-sm">
              {address && <p className="font-medium text-gray-900 mb-2">{address}</p>}
              <a
                href={openStreetMapUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-purple-600 hover:text-purple-700 transition-colors"
              >
                <ExternalLink className="w-3 h-3" />
                <span>Open in maps</span>
              </a>
            </div>
          </Popup>
        </Marker>
      </MapContainer>
    </div>
  );
}
