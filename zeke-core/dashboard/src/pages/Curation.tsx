import { useEffect, useState } from 'react';
import { Sparkles, Check, X, RefreshCw, AlertTriangle, Tag, Clock, BarChart3 } from 'lucide-react';
import { api, type Memory, type CurationStats, type CurationRun } from '../lib/api';

export function Curation() {
  const [stats, setStats] = useState<CurationStats | null>(null);
  const [flaggedMemories, setFlaggedMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningCuration, setRunningCuration] = useState(false);
  const [lastRun, setLastRun] = useState<CurationRun | null>(null);

  async function loadData() {
    try {
      const [statsData, memoriesData] = await Promise.all([
        api.getCurationStats(),
        api.getFlaggedMemories(),
      ]);
      setStats(statsData);
      setFlaggedMemories(memoriesData);
      if (statsData?.recent_runs && statsData.recent_runs.length > 0) {
        setLastRun(statsData.recent_runs[0]);
      }
    } catch (err) {
      console.error('Failed to load curation data:', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleRunCuration() {
    setRunningCuration(true);
    try {
      const result = await api.runCuration('default_user', 20, false, false);
      if (result) {
        setLastRun(result);
      }
      await loadData();
    } catch (err) {
      console.error('Failed to run curation:', err);
    } finally {
      setRunningCuration(false);
    }
  }

  async function handleApprove(memoryId: string) {
    const result = await api.approveMemory(memoryId);
    if (result) {
      setFlaggedMemories(prev => prev.filter(m => m.id !== memoryId));
      await loadData();
    }
  }

  async function handleReject(memoryId: string, permanent: boolean = false) {
    const success = await api.rejectMemory(memoryId, permanent);
    if (success) {
      setFlaggedMemories(prev => prev.filter(m => m.id !== memoryId));
      await loadData();
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-3">
            <Sparkles className="w-8 h-8 text-purple-400" />
            Memory Curation
          </h1>
          <p className="text-slate-400 mt-1">Clean, organize, and improve your memories</p>
        </div>
        <button
          onClick={handleRunCuration}
          disabled={runningCuration}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${runningCuration ? 'animate-spin' : ''}`} />
          {runningCuration ? 'Running...' : 'Run Curation'}
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatCard
            label="Total Memories"
            value={stats.total_memories}
            color="blue"
          />
          <StatCard
            label="Clean"
            value={stats.clean}
            color="green"
          />
          <StatCard
            label="Pending"
            value={stats.pending_curation}
            color="yellow"
          />
          <StatCard
            label="Needs Review"
            value={stats.needs_review}
            color="orange"
          />
          <StatCard
            label="Flagged"
            value={stats.flagged}
            color="red"
          />
        </div>
      )}

      {stats && (
        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
            <BarChart3 className="w-5 h-5 text-purple-400" />
            Curation Progress
          </h2>
          <div className="relative h-4 bg-slate-700 rounded-full overflow-hidden mb-2">
            <div
              className="absolute left-0 top-0 h-full bg-gradient-to-r from-purple-500 to-purple-400 transition-all duration-500"
              style={{ width: `${stats.curation_progress}%` }}
            />
          </div>
          <p className="text-slate-400 text-sm">
            {stats.curation_progress.toFixed(1)}% of memories have been curated
          </p>
        </div>
      )}

      {stats && Object.keys(stats.by_topic).length > 0 && (
        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
            <Tag className="w-5 h-5 text-purple-400" />
            Memories by Topic
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(stats.by_topic).map(([topic, count]) => (
              <div key={topic} className="bg-slate-800 rounded-lg p-3">
                <p className="text-slate-400 text-xs capitalize">{topic.replace(/_/g, ' ')}</p>
                <p className="text-white text-lg font-semibold">{count}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {lastRun && (
        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
            <Clock className="w-5 h-5 text-purple-400" />
            Last Curation Run
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-slate-800 rounded-lg p-3">
              <p className="text-slate-400 text-xs">Status</p>
              <p className={`text-lg font-semibold capitalize ${
                lastRun.status === 'completed' ? 'text-green-400' :
                lastRun.status === 'failed' ? 'text-red-400' :
                'text-yellow-400'
              }`}>{lastRun.status}</p>
            </div>
            <div className="bg-slate-800 rounded-lg p-3">
              <p className="text-slate-400 text-xs">Processed</p>
              <p className="text-white text-lg font-semibold">{lastRun.memories_processed}</p>
            </div>
            <div className="bg-slate-800 rounded-lg p-3">
              <p className="text-slate-400 text-xs">Updated</p>
              <p className="text-white text-lg font-semibold">{lastRun.memories_updated}</p>
            </div>
            <div className="bg-slate-800 rounded-lg p-3">
              <p className="text-slate-400 text-xs">Flagged</p>
              <p className="text-white text-lg font-semibold">{lastRun.memories_flagged}</p>
            </div>
          </div>
          <p className="text-slate-500 text-xs mt-3">
            Started: {new Date(lastRun.started_at).toLocaleString()}
          </p>
        </div>
      )}

      <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-orange-400" />
            Memories for Review ({flaggedMemories.length})
          </h2>
        </div>

        {flaggedMemories.length === 0 ? (
          <div className="text-center py-8">
            <Check className="w-12 h-12 text-green-400 mx-auto mb-3" />
            <p className="text-slate-400">All memories are clean! Nothing to review.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {flaggedMemories.map((memory) => (
              <MemoryReviewCard
                key={memory.id}
                memory={memory}
                onApprove={() => handleApprove(memory.id)}
                onReject={() => handleReject(memory.id, false)}
                onDelete={() => handleReject(memory.id, true)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-900/50 border-blue-700 text-blue-400',
    green: 'bg-green-900/50 border-green-700 text-green-400',
    red: 'bg-red-900/50 border-red-700 text-red-400',
    yellow: 'bg-yellow-900/50 border-yellow-700 text-yellow-400',
    orange: 'bg-orange-900/50 border-orange-700 text-orange-400',
  };

  return (
    <div className={`rounded-xl p-3 md:p-4 border ${colorClasses[color]}`}>
      <p className="text-2xl md:text-3xl font-bold">{value}</p>
      <p className="text-xs md:text-sm mt-1 opacity-80">{label}</p>
    </div>
  );
}

function MemoryReviewCard({
  memory,
  onApprove,
  onReject,
  onDelete,
}: {
  memory: Memory;
  onApprove: () => void;
  onReject: () => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const statusColors: Record<string, string> = {
    flagged: 'bg-red-600',
    needs_review: 'bg-orange-600',
    pending: 'bg-yellow-600',
  };

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={`px-2 py-0.5 text-xs rounded text-white ${statusColors[memory.curation_status || 'pending']}`}>
              {memory.curation_status?.replace(/_/g, ' ') || 'pending'}
            </span>
            {memory.primary_topic && (
              <span className="px-2 py-0.5 text-xs rounded bg-slate-700 text-slate-300 capitalize">
                {memory.primary_topic.replace(/_/g, ' ')}
              </span>
            )}
            {memory.curation_confidence !== undefined && (
              <span className="text-xs text-slate-500">
                {(memory.curation_confidence * 100).toFixed(0)}% confidence
              </span>
            )}
          </div>
          <p className={`text-slate-200 text-sm ${expanded ? '' : 'line-clamp-2'}`}>
            {memory.content}
          </p>
          {memory.content.length > 100 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-purple-400 text-xs mt-1 hover:underline"
            >
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
          {memory.curation_notes && (
            <p className="text-orange-400 text-xs mt-2 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              {memory.curation_notes}
            </p>
          )}
          <p className="text-slate-500 text-xs mt-2">
            Created: {new Date(memory.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <button
            onClick={onApprove}
            className="p-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors"
            title="Approve"
          >
            <Check className="w-4 h-4" />
          </button>
          <button
            onClick={onReject}
            className="p-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors"
            title="Mark as rejected"
          >
            <X className="w-4 h-4" />
          </button>
          <button
            onClick={onDelete}
            className="p-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
            title="Delete permanently"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
