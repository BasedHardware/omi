import { useState, useEffect, useMemo } from 'react';
import { Plus, Trash2, Search, Brain, X, Filter, Calendar, Tag, Sparkles, ChevronDown, ChevronUp, Check, RefreshCw, AlertTriangle, Clock, BarChart3, Zap, Shield, Eye } from 'lucide-react';
import { api, type Memory, type CurationStats, type CurationRun } from '../lib/api';

type TabType = 'browse' | 'add' | 'curate';

export function Memories() {
  const [activeTab, setActiveTab] = useState<TabType>('browse');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [newMemory, setNewMemory] = useState('');
  const [creating, setCreating] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [expandedMemories, setExpandedMemories] = useState<Set<string>>(new Set());
  
  const [stats, setStats] = useState<CurationStats | null>(null);
  const [flaggedMemories, setFlaggedMemories] = useState<Memory[]>([]);
  const [runningCuration, setRunningCuration] = useState(false);
  const [lastRun, setLastRun] = useState<CurationRun | null>(null);
  const [curationView, setCurationView] = useState<'overview' | 'review'>('overview');

  useEffect(() => {
    loadMemories();
    loadCurationData();
  }, []);

  async function loadMemories() {
    try {
      const data = await api.getMemories(100);
      setMemories(data);
    } catch (err) {
      console.error('Failed to load memories:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadCurationData() {
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
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    
    setIsSearching(true);
    try {
      const results = await api.searchMemories(searchQuery);
      setSearchResults(results);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setIsSearching(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newMemory.trim() || creating) return;
    
    setCreating(true);
    try {
      const memory = await api.createMemory(newMemory);
      setMemories([memory, ...memories]);
      setNewMemory('');
      setActiveTab('browse');
    } catch (err) {
      console.error('Failed to create memory:', err);
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Are you sure you want to delete this memory?')) return;
    
    try {
      await api.deleteMemory(id);
      setMemories(memories.filter((m) => m.id !== id));
    } catch (err) {
      console.error('Failed to delete memory:', err);
    }
  }

  async function handleRunCuration() {
    setRunningCuration(true);
    try {
      const result = await api.runCuration('default_user', 20, false, false);
      if (result) {
        setLastRun(result);
      }
      await loadCurationData();
      await loadMemories();
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
      await loadCurationData();
    }
  }

  async function handleReject(memoryId: string, permanent: boolean = false) {
    const success = await api.rejectMemory(memoryId, permanent);
    if (success) {
      setFlaggedMemories(prev => prev.filter(m => m.id !== memoryId));
      await loadCurationData();
    }
  }

  function toggleExpanded(id: string) {
    const newExpanded = new Set(expandedMemories);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedMemories(newExpanded);
  }

  const { categoryCounts, uniqueCategories } = useMemo(() => {
    const counts: Record<string, number> = {};
    const categorySet = new Set<string>();
    let manualCount = 0;
    
    memories.forEach((m) => {
      const cat = m.category?.toLowerCase() || 'other';
      counts[cat] = (counts[cat] || 0) + 1;
      categorySet.add(cat);
      if (m.manually_added) {
        manualCount++;
      }
    });
    
    categorySet.delete('manual');
    
    const sortedCategories = Array.from(categorySet).sort();
    const categories = ['all', ...sortedCategories];
    
    if (manualCount > 0) {
      counts['manual'] = manualCount;
      categories.push('manual');
    }
    
    return { categoryCounts: counts, uniqueCategories: categories };
  }, [memories]);

  const filteredMemories = useMemo(() => {
    if (selectedCategory === 'all') return memories;
    if (selectedCategory === 'manual') return memories.filter(m => m.manually_added);
    return memories.filter(m => (m.category?.toLowerCase() || 'other') === selectedCategory);
  }, [memories, selectedCategory]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse flex flex-col items-center gap-3">
          <Brain className="w-12 h-12 text-cyan-400 animate-bounce" />
          <p className="text-slate-400">Loading memories...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl">
              <Brain className="w-6 h-6 text-white" />
            </div>
            Memory
          </h1>
          <p className="text-slate-400 mt-2 text-sm md:text-base">
            {memories.length} memories • {stats?.pending_curation || 0} pending • {flaggedMemories.length} to review
          </p>
        </div>
      </div>

      <div className="flex bg-slate-800/50 rounded-xl p-1 border border-slate-700">
        <button
          onClick={() => setActiveTab('browse')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'browse'
              ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Search className="w-4 h-4" />
          Browse
        </button>
        <button
          onClick={() => setActiveTab('add')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'add'
              ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Plus className="w-4 h-4" />
          Add
        </button>
        <button
          onClick={() => setActiveTab('curate')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'curate'
              ? 'bg-gradient-to-r from-purple-500 to-pink-600 text-white shadow-lg'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Sparkles className="w-4 h-4" />
          Curate
          {flaggedMemories.length > 0 && (
            <span className="bg-orange-500 text-white text-xs px-1.5 py-0.5 rounded-full min-w-[18px]">
              {flaggedMemories.length}
            </span>
          )}
        </button>
      </div>

      {activeTab === 'browse' && (
        <BrowseTab
          memories={filteredMemories}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          searchResults={searchResults}
          setSearchResults={setSearchResults}
          isSearching={isSearching}
          handleSearch={handleSearch}
          showFilters={showFilters}
          setShowFilters={setShowFilters}
          selectedCategory={selectedCategory}
          setSelectedCategory={setSelectedCategory}
          uniqueCategories={uniqueCategories}
          categoryCounts={categoryCounts}
          expandedMemories={expandedMemories}
          toggleExpanded={toggleExpanded}
          handleDelete={handleDelete}
        />
      )}

      {activeTab === 'add' && (
        <AddTab
          newMemory={newMemory}
          setNewMemory={setNewMemory}
          creating={creating}
          handleCreate={handleCreate}
        />
      )}

      {activeTab === 'curate' && (
        <CurateTab
          stats={stats}
          flaggedMemories={flaggedMemories}
          lastRun={lastRun}
          runningCuration={runningCuration}
          curationView={curationView}
          setCurationView={setCurationView}
          handleRunCuration={handleRunCuration}
          handleApprove={handleApprove}
          handleReject={handleReject}
        />
      )}
    </div>
  );
}

function BrowseTab({
  memories,
  searchQuery,
  setSearchQuery,
  searchResults,
  setSearchResults,
  isSearching,
  handleSearch,
  showFilters,
  setShowFilters,
  selectedCategory,
  setSelectedCategory,
  uniqueCategories,
  categoryCounts,
  expandedMemories,
  toggleExpanded,
  handleDelete,
}: {
  memories: Memory[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  searchResults: string[];
  setSearchResults: (r: string[]) => void;
  isSearching: boolean;
  handleSearch: (e: React.FormEvent) => void;
  showFilters: boolean;
  setShowFilters: (s: boolean) => void;
  selectedCategory: string;
  setSelectedCategory: (c: string) => void;
  uniqueCategories: string[];
  categoryCounts: Record<string, number>;
  expandedMemories: Set<string>;
  toggleExpanded: (id: string) => void;
  handleDelete: (id: string) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row gap-3">
        <form onSubmit={handleSearch} className="flex-1 flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search your memories..."
              className="w-full bg-slate-800/80 text-white rounded-xl pl-11 pr-4 py-3 border border-slate-700 focus:outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 text-base transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={isSearching || !searchQuery.trim()}
            className="bg-slate-700 text-white px-5 py-3 rounded-xl hover:bg-slate-600 active:bg-slate-500 transition-all disabled:opacity-50"
          >
            {isSearching ? '...' : 'Search'}
          </button>
        </form>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-4 py-3 rounded-xl transition-all ${
            showFilters || selectedCategory !== 'all'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          }`}
        >
          <Filter className="w-5 h-5" />
          <span className="hidden md:inline">Filter</span>
          {selectedCategory !== 'all' && (
            <span className="bg-cyan-500 text-white text-xs px-2 py-0.5 rounded-full">1</span>
          )}
        </button>
      </div>

      {showFilters && (
        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
          <p className="text-sm text-slate-400 mb-3">Filter by category</p>
          <div className="flex flex-wrap gap-2">
            {uniqueCategories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  selectedCategory === cat
                    ? 'bg-cyan-500 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {cat.charAt(0).toUpperCase() + cat.slice(1)}
                {cat !== 'all' && categoryCounts[cat] !== undefined && (
                  <span className="ml-1.5 text-xs opacity-70">({categoryCounts[cat]})</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {searchResults.length > 0 && (
        <div className="bg-gradient-to-br from-cyan-900/30 to-blue-900/30 border border-cyan-700/50 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base md:text-lg font-semibold text-cyan-300 flex items-center gap-2">
              <Search className="w-5 h-5" />
              Search Results ({searchResults.length})
            </h2>
            <button
              onClick={() => setSearchResults([])}
              className="text-cyan-400 text-sm hover:underline flex items-center gap-1"
            >
              <X className="w-4 h-4" />
              Clear
            </button>
          </div>
          <ul className="space-y-2">
            {searchResults.map((result, index) => (
              <li key={index} className="p-3.5 bg-cyan-900/40 rounded-xl text-cyan-100 text-sm md:text-base border border-cyan-800/30">
                {result}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-3">
        {memories.length === 0 ? (
          <div className="bg-slate-800/50 rounded-2xl p-12 text-center border border-slate-700/50">
            <div className="w-16 h-16 bg-slate-700/50 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Brain className="w-8 h-8 text-slate-500" />
            </div>
            <p className="text-slate-400 font-medium">No memories yet</p>
            <p className="text-slate-500 text-sm mt-2">
              Memories are automatically extracted from your conversations
            </p>
          </div>
        ) : (
          memories.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              expanded={expandedMemories.has(memory.id)}
              onToggle={() => toggleExpanded(memory.id)}
              onDelete={() => handleDelete(memory.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function AddTab({
  newMemory,
  setNewMemory,
  creating,
  handleCreate,
}: {
  newMemory: string;
  setNewMemory: (m: string) => void;
  creating: boolean;
  handleCreate: (e: React.FormEvent) => void;
}) {
  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-6 border border-slate-700 shadow-xl">
      <div className="flex items-center gap-3 mb-5">
        <div className="p-2.5 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl">
          <Sparkles className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">Create Memory</h2>
          <p className="text-sm text-slate-400">Add a new memory for Zeke to remember</p>
        </div>
      </div>
      <form onSubmit={handleCreate} className="space-y-4">
        <textarea
          value={newMemory}
          onChange={(e) => setNewMemory(e.target.value)}
          placeholder="What would you like Zeke to remember? Write in natural language - things about yourself, your preferences, important facts, or anything you want Zeke to know..."
          className="w-full bg-slate-900/80 text-white rounded-xl px-4 py-4 border border-slate-600 focus:outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 min-h-[180px] text-base resize-none transition-all placeholder:text-slate-500"
          autoFocus
        />
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            type="submit"
            disabled={creating || !newMemory.trim()}
            className="flex-1 bg-gradient-to-r from-cyan-500 to-blue-600 text-white px-5 py-3 rounded-xl hover:from-cyan-600 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium flex items-center justify-center gap-2"
          >
            {creating ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                Save Memory
              </>
            )}
          </button>
        </div>
      </form>
      
      <div className="mt-6 p-4 bg-slate-900/50 rounded-xl border border-slate-700/50">
        <p className="text-xs text-slate-500 mb-2">Tips for good memories:</p>
        <ul className="text-xs text-slate-400 space-y-1">
          <li>• Be specific and descriptive</li>
          <li>• Include context when helpful</li>
          <li>• Use first person (I, my, me)</li>
          <li>• One idea per memory works best</li>
        </ul>
      </div>
    </div>
  );
}

function CurateTab({
  stats,
  flaggedMemories,
  lastRun,
  runningCuration,
  curationView,
  setCurationView,
  handleRunCuration,
  handleApprove,
  handleReject,
}: {
  stats: CurationStats | null;
  flaggedMemories: Memory[];
  lastRun: CurationRun | null;
  runningCuration: boolean;
  curationView: 'overview' | 'review';
  setCurationView: (v: 'overview' | 'review') => void;
  handleRunCuration: () => void;
  handleApprove: (id: string) => void;
  handleReject: (id: string, permanent: boolean) => void;
}) {
  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex bg-slate-800/50 rounded-lg p-1 border border-slate-700 flex-1 max-w-xs">
          <button
            onClick={() => setCurationView('overview')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-sm font-medium transition-all ${
              curationView === 'overview'
                ? 'bg-gradient-to-r from-purple-500 to-pink-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            Stats
          </button>
          <button
            onClick={() => setCurationView('review')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-sm font-medium transition-all ${
              curationView === 'review'
                ? 'bg-gradient-to-r from-purple-500 to-pink-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Eye className="w-4 h-4" />
            Review
            {flaggedMemories.length > 0 && (
              <span className="bg-orange-500 text-white text-xs px-1.5 py-0.5 rounded-full">
                {flaggedMemories.length}
              </span>
            )}
          </button>
        </div>
        <button
          onClick={handleRunCuration}
          disabled={runningCuration}
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-purple-500 to-pink-600 hover:from-purple-600 hover:to-pink-700 disabled:from-purple-800 disabled:to-pink-800 disabled:cursor-not-allowed text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 active:scale-95 text-sm"
        >
          <RefreshCw className={`w-4 h-4 ${runningCuration ? 'animate-spin' : ''}`} />
          {runningCuration ? 'Running...' : 'Run Curation'}
        </button>
      </div>

      {curationView === 'overview' && (
        <div className="space-y-4">
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

      {curationView === 'review' && (
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

function MemoryCard({
  memory,
  expanded,
  onToggle,
  onDelete,
}: {
  memory: Memory;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const isLongContent = memory.content.length > 150;

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      personal: 'from-purple-500 to-pink-500',
      work: 'from-blue-500 to-cyan-500',
      health: 'from-green-500 to-emerald-500',
      relationships: 'from-rose-500 to-orange-500',
      goals: 'from-amber-500 to-yellow-500',
      manual: 'from-cyan-500 to-blue-500',
      default: 'from-slate-500 to-slate-600',
    };
    return colors[category?.toLowerCase()] || colors.default;
  };

  return (
    <div className="bg-gradient-to-br from-slate-800/80 to-slate-900/80 rounded-2xl p-4 border border-slate-700/50 hover:border-slate-600 transition-all group">
      <div className="flex items-start gap-3">
        <div className={`w-1 self-stretch rounded-full bg-gradient-to-b ${getCategoryColor(memory.category)}`} />
        
        <div className="flex-1 min-w-0">
          <p className={`text-slate-200 text-sm md:text-base leading-relaxed ${
            !expanded && isLongContent ? 'line-clamp-3' : ''
          }`}>
            {memory.content}
          </p>
          
          {isLongContent && (
            <button
              onClick={onToggle}
              className="mt-2 text-cyan-400 text-sm hover:text-cyan-300 flex items-center gap-1 transition-colors"
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
          
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <span className="flex items-center gap-1.5 text-xs text-slate-500">
              <Calendar className="w-3.5 h-3.5" />
              {new Date(memory.created_at).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}
            </span>
            <span className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-gradient-to-r ${getCategoryColor(memory.category)} text-white`}>
              <Tag className="w-3 h-3" />
              {memory.category || 'uncategorized'}
            </span>
            {memory.manually_added && (
              <span className="text-xs px-2 py-1 bg-cyan-500/20 text-cyan-400 rounded-full border border-cyan-500/30">
                Manual
              </span>
            )}
            {memory.primary_topic && (
              <span className="text-xs px-2 py-1 bg-slate-700 text-slate-300 rounded-full">
                {memory.primary_topic.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        </div>
        
        <button
          onClick={onDelete}
          className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
        >
          <Trash2 className="w-5 h-5" />
        </button>
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
