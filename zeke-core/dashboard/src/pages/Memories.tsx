import { useState, useEffect, useMemo } from 'react';
import { Plus, Trash2, Search, Brain, X, Filter, Calendar, Tag, Sparkles, ChevronDown, ChevronUp } from 'lucide-react';
import { api, type Memory } from '../lib/api';

export function Memories() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newMemory, setNewMemory] = useState('');
  const [creating, setCreating] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [expandedMemories, setExpandedMemories] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadMemories();
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
      setShowAddForm(false);
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
            Memories
          </h1>
          <p className="text-slate-400 mt-2 text-sm md:text-base">
            {memories.length} memories stored
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-2 bg-gradient-to-r from-cyan-500 to-blue-600 text-white px-4 py-2.5 rounded-xl hover:from-cyan-600 hover:to-blue-700 active:scale-95 transition-all shadow-lg shadow-cyan-500/25"
        >
          <Plus className="w-5 h-5" />
          <span className="hidden md:inline font-medium">Add Memory</span>
        </button>
      </div>

      {showAddForm && (
        <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-5 border border-slate-700 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-cyan-400" />
              Create Memory
            </h2>
            <button
              onClick={() => setShowAddForm(false)}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-all"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <form onSubmit={handleCreate} className="space-y-4">
            <textarea
              value={newMemory}
              onChange={(e) => setNewMemory(e.target.value)}
              placeholder="What would you like Zeke to remember?"
              className="w-full bg-slate-900/80 text-white rounded-xl px-4 py-3 border border-slate-600 focus:outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 min-h-[120px] text-base resize-none transition-all"
              autoFocus
            />
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-all"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating || !newMemory.trim()}
                className="bg-gradient-to-r from-cyan-500 to-blue-600 text-white px-5 py-2.5 rounded-xl hover:from-cyan-600 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium"
              >
                {creating ? 'Saving...' : 'Save Memory'}
              </button>
            </div>
          </form>
        </div>
      )}

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
        {filteredMemories.length === 0 ? (
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
          filteredMemories.map((memory) => (
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
