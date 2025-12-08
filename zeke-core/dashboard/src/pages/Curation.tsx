import { useEffect, useState } from 'react';
import { Sparkles, Check, X, RefreshCw, AlertTriangle, Tag, Clock, BarChart3, Trash2, ChevronDown, ChevronUp, Zap, Shield, Eye } from 'lucide-react';
import { api, type Memory, type CurationStats, type CurationRun } from '../lib/api';

export function Curation() {
  const [stats, setStats] = useState<CurationStats | null>(null);
  const [flaggedMemories, setFlaggedMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningCuration, setRunningCuration] = useState(false);
  const [lastRun, setLastRun] = useState<CurationRun | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'review'>('overview');

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
        <div className="animate-pulse flex flex-col items-center gap-3">
          <Sparkles className="w-12 h-12 text-purple-400 animate-pulse" />
          <p className="text-slate-400">Loading curation data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-purple-500 to-pink-600 rounded-xl">
              <Sparkles className="w-6 h-6 text-white" />
            </div>
            Memory Curation
          </h1>
          <p className="text-slate-400 mt-2">Clean, organize, and improve your memories</p>
        </div>
        <button
          onClick={handleRunCuration}
          disabled={runningCuration}
          className="flex items-center justify-center gap-2 px-5 py-2.5 bg-gradient-to-r from-purple-500 to-pink-600 hover:from-purple-600 hover:to-pink-700 disabled:from-purple-800 disabled:to-pink-800 disabled:cursor-not-allowed text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 active:scale-95"
        >
          <RefreshCw className={`w-5 h-5 ${runningCuration ? 'animate-spin' : ''}`} />
          {runningCuration ? 'Running...' : 'Run Curation'}
        </button>
      </div>

      <div className="flex bg-slate-800/50 rounded-xl p-1 border border-slate-700">
        <button
          onClick={() => setActiveTab('overview')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'overview'
              ? 'bg-gradient-to-r from-purple-500 to-pink-600 text-white shadow-lg'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          Overview
        </button>
        <button
          onClick={() => setActiveTab('review')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'review'
              ? 'bg-gradient-to-r from-purple-500 to-pink-600 text-white shadow-lg'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Eye className="w-4 h-4" />
          Review
          {flaggedMemories.length > 0 && (
            <span className="bg-orange-500 text-white text-xs px-2 py-0.5 rounded-full">
              {flaggedMemories.length}
            </span>
          )}
        </button>
      </div>

      {activeTab === 'overview' && (
        <div className="space-y-5">
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <StatCard
                label="Total"
                value={stats.total_memories}
                icon={<Tag className="w-5 h-5" />}
                gradient="from-blue-500 to-cyan-500"
              />
              <StatCard
                label="Clean"
                value={stats.clean}
                icon={<Shield className="w-5 h-5" />}
                gradient="from-green-500 to-emerald-500"
              />
              <StatCard
                label="Pending"
                value={stats.pending_curation}
                icon={<Clock className="w-5 h-5" />}
                gradient="from-yellow-500 to-amber-500"
              />
              <StatCard
                label="Review"
                value={stats.needs_review}
                icon={<Eye className="w-5 h-5" />}
                gradient="from-orange-500 to-red-500"
              />
              <StatCard
                label="Flagged"
                value={stats.flagged}
                icon={<AlertTriangle className="w-5 h-5" />}
                gradient="from-red-500 to-pink-500"
              />
            </div>
          )}

          {stats && (
            <div className="bg-gradient-to-br from-slate-800/80 to-slate-900/80 rounded-2xl p-5 border border-slate-700/50">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
                <Zap className="w-5 h-5 text-purple-400" />
                Curation Progress
              </h2>
              <div className="relative h-4 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="absolute left-0 top-0 h-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all duration-500 rounded-full"
                  style={{ width: `${stats.curation_progress}%` }}
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xs font-medium text-white drop-shadow-md">
                    {stats.curation_progress.toFixed(1)}%
                  </span>
                </div>
              </div>
              <p className="text-slate-400 text-sm mt-3">
                {stats.clean} of {stats.total_memories} memories have been curated
              </p>
            </div>
          )}

          {stats && Object.keys(stats.by_topic).length > 0 && (
            <div className="bg-gradient-to-br from-slate-800/80 to-slate-900/80 rounded-2xl p-5 border border-slate-700/50">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
                <Tag className="w-5 h-5 text-purple-400" />
                Memories by Topic
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(stats.by_topic)
                  .sort(([, a], [, b]) => b - a)
                  .map(([topic, count]) => (
                    <TopicCard key={topic} topic={topic} count={count} total={stats.total_memories} />
                  ))}
              </div>
            </div>
          )}

          {lastRun && (
            <div className="bg-gradient-to-br from-slate-800/80 to-slate-900/80 rounded-2xl p-5 border border-slate-700/50">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
                <Clock className="w-5 h-5 text-purple-400" />
                Last Curation Run
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-slate-800/80 rounded-xl p-4 border border-slate-700/50">
                  <p className="text-slate-400 text-xs uppercase tracking-wide">Status</p>
                  <p className={`text-lg font-semibold capitalize mt-1 ${
                    lastRun.status === 'completed' ? 'text-green-400' :
                    lastRun.status === 'failed' ? 'text-red-400' :
                    'text-yellow-400'
                  }`}>{lastRun.status}</p>
                </div>
                <div className="bg-slate-800/80 rounded-xl p-4 border border-slate-700/50">
                  <p className="text-slate-400 text-xs uppercase tracking-wide">Processed</p>
                  <p className="text-white text-lg font-semibold mt-1">{lastRun.memories_processed}</p>
                </div>
                <div className="bg-slate-800/80 rounded-xl p-4 border border-slate-700/50">
                  <p className="text-slate-400 text-xs uppercase tracking-wide">Updated</p>
                  <p className="text-white text-lg font-semibold mt-1">{lastRun.memories_updated}</p>
                </div>
                <div className="bg-slate-800/80 rounded-xl p-4 border border-slate-700/50">
                  <p className="text-slate-400 text-xs uppercase tracking-wide">Flagged</p>
                  <p className="text-white text-lg font-semibold mt-1">{lastRun.memories_flagged}</p>
                </div>
              </div>
              <p className="text-slate-500 text-xs mt-4 flex items-center gap-2">
                <Clock className="w-3.5 h-3.5" />
                {new Date(lastRun.started_at).toLocaleString()}
              </p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'review' && (
        <div className="space-y-4">
          {flaggedMemories.length === 0 ? (
            <div className="bg-gradient-to-br from-green-900/30 to-emerald-900/30 rounded-2xl p-12 text-center border border-green-700/30">
              <div className="w-16 h-16 bg-green-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <Check className="w-8 h-8 text-green-400" />
              </div>
              <h3 className="text-lg font-semibold text-green-300">All Clear!</h3>
              <p className="text-slate-400 mt-2">All memories have been reviewed. Nothing needs attention.</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <p className="text-slate-400">
                  {flaggedMemories.length} {flaggedMemories.length === 1 ? 'memory' : 'memories'} need review
                </p>
              </div>
              {flaggedMemories.map((memory) => (
                <MemoryReviewCard
                  key={memory.id}
                  memory={memory}
                  onApprove={() => handleApprove(memory.id)}
                  onReject={() => handleReject(memory.id, false)}
                  onDelete={() => handleReject(memory.id, true)}
                />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({ 
  label, 
  value, 
  icon, 
  gradient 
}: { 
  label: string; 
  value: number; 
  icon: React.ReactNode;
  gradient: string;
}) {
  return (
    <div className="bg-gradient-to-br from-slate-800/80 to-slate-900/80 rounded-2xl p-4 border border-slate-700/50 group hover:border-slate-600 transition-all">
      <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center text-white mb-3`}>
        {icon}
      </div>
      <p className="text-2xl md:text-3xl font-bold text-white">{value}</p>
      <p className="text-sm text-slate-400 mt-1">{label}</p>
    </div>
  );
}

function TopicCard({ topic, count, total }: { topic: string; count: number; total: number }) {
  const percentage = total > 0 ? (count / total) * 100 : 0;
  
  return (
    <div className="bg-slate-800/80 rounded-xl p-4 border border-slate-700/50 hover:border-slate-600 transition-all">
      <p className="text-slate-300 text-sm capitalize font-medium">{topic.replace(/_/g, ' ')}</p>
      <div className="flex items-end justify-between mt-2">
        <p className="text-white text-xl font-bold">{count}</p>
        <p className="text-slate-500 text-xs">{percentage.toFixed(0)}%</p>
      </div>
      <div className="h-1 bg-slate-700 rounded-full mt-2 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full transition-all"
          style={{ width: `${percentage}%` }}
        />
      </div>
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
  const isLongContent = memory.content.length > 150;

  const statusConfig: Record<string, { bg: string; text: string; border: string }> = {
    flagged: { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30' },
    needs_review: { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/30' },
    pending: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  };

  const status = memory.curation_status || 'pending';
  const config = statusConfig[status] || statusConfig.pending;

  return (
    <div className="bg-gradient-to-br from-slate-800/80 to-slate-900/80 rounded-2xl p-5 border border-slate-700/50 hover:border-slate-600 transition-all">
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className={`px-2.5 py-1 text-xs rounded-lg font-medium ${config.bg} ${config.text} border ${config.border}`}>
              {status.replace(/_/g, ' ')}
            </span>
            {memory.primary_topic && (
              <span className="px-2.5 py-1 text-xs rounded-lg bg-slate-700 text-slate-300 capitalize">
                {memory.primary_topic.replace(/_/g, ' ')}
              </span>
            )}
            {memory.curation_confidence !== undefined && (
              <span className="text-xs text-slate-500">
                {(memory.curation_confidence * 100).toFixed(0)}% confidence
              </span>
            )}
          </div>
          
          <p className={`text-slate-200 text-sm md:text-base leading-relaxed ${
            !expanded && isLongContent ? 'line-clamp-3' : ''
          }`}>
            {memory.content}
          </p>
          
          {isLongContent && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-2 text-purple-400 text-sm hover:text-purple-300 flex items-center gap-1 transition-colors"
            >
              {expanded ? (
                <>
                  <ChevronUp className="w-4 h-4" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown className="w-4 h-4" />
                  Show more
                </>
              )}
            </button>
          )}
          
          {memory.curation_notes && (
            <div className="mt-3 p-3 bg-orange-500/10 border border-orange-500/20 rounded-xl">
              <p className="text-orange-400 text-sm flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                {memory.curation_notes}
              </p>
            </div>
          )}
          
          <p className="text-slate-500 text-xs mt-3 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />
            {new Date(memory.created_at).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </p>
        </div>
        
        <div className="flex flex-col gap-2">
          <button
            onClick={onApprove}
            className="p-3 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-xl transition-all border border-green-500/30"
            title="Approve"
          >
            <Check className="w-5 h-5" />
          </button>
          <button
            onClick={onReject}
            className="p-3 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 rounded-xl transition-all border border-yellow-500/30"
            title="Mark as rejected"
          >
            <X className="w-5 h-5" />
          </button>
          <button
            onClick={onDelete}
            className="p-3 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-xl transition-all border border-red-500/30"
            title="Delete permanently"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
