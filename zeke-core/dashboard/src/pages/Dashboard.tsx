import { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Brain, CheckSquare, Clock, AlertTriangle, MapPin, Battery, Navigation } from 'lucide-react';
import { api, type Memory, type Task, type LocationContext } from '../lib/api';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

function LocationMap({ lat, lng }: { lat: number; lng: number }) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);

  useEffect(() => {
    if (!mapRef.current) return;

    if (!mapInstanceRef.current) {
      mapInstanceRef.current = L.map(mapRef.current, {
        zoomControl: false,
        attributionControl: true,
      }).setView([lat, lng], 15);

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap'
      }).addTo(mapInstanceRef.current);

      const icon = L.icon({
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
      });

      markerRef.current = L.marker([lat, lng], { icon }).addTo(mapInstanceRef.current);
    } else {
      mapInstanceRef.current.setView([lat, lng], 15);
      markerRef.current?.setLatLng([lat, lng]);
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
        markerRef.current = null;
      }
    };
  }, [lat, lng]);

  return <div ref={mapRef} className="h-full w-full" />;
}

export function Dashboard() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [overdueTasks, setOverdueTasks] = useState<Task[]>([]);
  const [dueSoonTasks, setDueSoonTasks] = useState<Task[]>([]);
  const [locationContext, setLocationContext] = useState<LocationContext | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [memoriesData, tasksData, overdueData, dueSoonData, locationData] = await Promise.all([
          api.getMemories(5),
          api.getTasks('pending', 5),
          api.getOverdueTasks(),
          api.getTasksDueSoon(24),
          api.getLocationContext(),
        ]);
        setMemories(memoriesData);
        setTasks(tasksData);
        setOverdueTasks(overdueData);
        setDueSoonTasks(dueSoonData);
        setLocationContext(locationData);
      } catch (err) {
        console.error('Failed to load dashboard data:', err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-white">Welcome back, Nate</h1>
        <p className="text-slate-400 mt-1 text-sm md:text-base">Here's what's happening today.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <StatCard
          icon={Brain}
          label="Memories"
          value={memories.length}
          color="blue"
        />
        <StatCard
          icon={CheckSquare}
          label="Tasks"
          value={tasks.length}
          color="green"
        />
        <StatCard
          icon={AlertTriangle}
          label="Overdue"
          value={overdueTasks.length}
          color={overdueTasks.length > 0 ? 'red' : 'slate'}
        />
        <StatCard
          icon={Clock}
          label="Due Soon"
          value={dueSoonTasks.length}
          color={dueSoonTasks.length > 0 ? 'yellow' : 'slate'}
        />
      </div>

      {locationContext && (
        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <MapPin className="w-5 h-5 text-purple-400" />
              Location
            </h2>
            <span className="text-xs text-slate-500">
              {new Date(locationContext.last_updated).toLocaleTimeString()}
            </span>
          </div>
          
          <div className="h-48 md:h-64 rounded-lg overflow-hidden mb-4">
            <LocationMap 
              lat={locationContext.current_latitude} 
              lng={locationContext.current_longitude} 
            />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-slate-800 rounded-lg p-3">
              <div className="flex items-center gap-2 text-purple-400 mb-1">
                <Navigation className="w-4 h-4" />
                <span className="text-xs">Motion</span>
              </div>
              <p className="text-slate-200 font-medium capitalize">{locationContext.current_motion}</p>
            </div>
            <div className="bg-slate-800 rounded-lg p-3">
              <div className="flex items-center gap-2 text-blue-400 mb-1">
                <MapPin className="w-4 h-4" />
                <span className="text-xs">Status</span>
              </div>
              <p className="text-slate-200 font-medium">
                {locationContext.is_at_home ? 'At Home' : locationContext.is_traveling ? 'Traveling' : 'Away'}
              </p>
            </div>
            {locationContext.current_speed !== null && locationContext.current_speed > 0 && (
              <div className="bg-slate-800 rounded-lg p-3">
                <div className="flex items-center gap-2 text-green-400 mb-1">
                  <Navigation className="w-4 h-4" />
                  <span className="text-xs">Speed</span>
                </div>
                <p className="text-slate-200 font-medium">{Math.round(locationContext.current_speed * 2.237)} mph</p>
              </div>
            )}
            {locationContext.battery_level !== null && (
              <div className="bg-slate-800 rounded-lg p-3">
                <div className="flex items-center gap-2 text-yellow-400 mb-1">
                  <Battery className="w-4 h-4" />
                  <span className="text-xs">Battery</span>
                </div>
                <p className="text-slate-200 font-medium">
                  {Math.round(locationContext.battery_level * 100)}%
                  {locationContext.battery_state === 'charging' && ' (charging)'}
                </p>
              </div>
            )}
          </div>
          {locationContext.location_description && (
            <p className="text-slate-400 text-sm mt-3">{locationContext.location_description}</p>
          )}
        </div>
      )}

      {overdueTasks.length > 0 && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4">
          <h2 className="text-base font-semibold text-red-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Overdue Tasks
          </h2>
          <ul className="mt-3 space-y-2">
            {overdueTasks.slice(0, 3).map((task) => (
              <li key={task.id} className="p-3 bg-red-900/50 rounded-lg">
                <p className="text-red-200 text-sm">{task.title}</p>
                {task.due_at && (
                  <p className="text-red-400 text-xs mt-1">
                    Was due: {new Date(task.due_at).toLocaleDateString()}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {overdueTasks.length > 3 && (
            <Link to="/tasks" className="text-red-400 text-sm mt-3 inline-block hover:underline">
              +{overdueTasks.length - 3} more
            </Link>
          )}
        </div>
      )}

      <div className="space-y-6 md:grid md:grid-cols-2 md:gap-6 md:space-y-0">
        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Recent Memories</h2>
            <Link to="/memories" className="text-blue-400 text-sm hover:underline">
              View all
            </Link>
          </div>
          {memories.length === 0 ? (
            <p className="text-slate-400 text-sm">No memories yet.</p>
          ) : (
            <ul className="space-y-3">
              {memories.map((memory) => (
                <li key={memory.id} className="p-3 bg-slate-800 rounded-lg">
                  <p className="text-slate-200 text-sm line-clamp-2">{memory.content}</p>
                  <p className="text-slate-500 text-xs mt-1">
                    {new Date(memory.created_at).toLocaleDateString()}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Pending Tasks</h2>
            <Link to="/tasks" className="text-blue-400 text-sm hover:underline">
              View all
            </Link>
          </div>
          {tasks.length === 0 ? (
            <p className="text-slate-400 text-sm">No pending tasks.</p>
          ) : (
            <ul className="space-y-3">
              {tasks.map((task) => (
                <li key={task.id} className="p-3 bg-slate-800 rounded-lg">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-slate-200 font-medium text-sm truncate">{task.title}</p>
                      {task.due_at && (
                        <p className="text-slate-500 text-xs mt-1">
                          Due: {new Date(task.due_at).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                    <PriorityBadge priority={task.priority} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: {
  icon: typeof Brain;
  label: string;
  value: number | string;
  color: string;
}) {
  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-900/50 border-blue-700 text-blue-400',
    green: 'bg-green-900/50 border-green-700 text-green-400',
    red: 'bg-red-900/50 border-red-700 text-red-400',
    yellow: 'bg-yellow-900/50 border-yellow-700 text-yellow-400',
    slate: 'bg-slate-900/50 border-slate-700 text-slate-400',
  };

  return (
    <div className={`rounded-xl p-3 md:p-4 border ${colorClasses[color]}`}>
      <div className="flex items-center justify-between">
        <Icon className="w-5 h-5 md:w-6 md:h-6" />
        <span className="text-xl md:text-2xl font-bold">{value}</span>
      </div>
      <p className="text-xs md:text-sm mt-2 opacity-80">{label}</p>
    </div>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    low: 'bg-slate-600 text-slate-200',
    medium: 'bg-blue-600 text-blue-100',
    high: 'bg-orange-600 text-orange-100',
    urgent: 'bg-red-600 text-red-100',
  };

  return (
    <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${colors[priority] || colors.medium}`}>
      {priority}
    </span>
  );
}
