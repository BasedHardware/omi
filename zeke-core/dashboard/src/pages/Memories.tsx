import { useState, useEffect } from 'react';
import { Plus, Trash2, Search, Brain, X } from 'lucide-react';
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

  useEffect(() => {
    loadMemories();
  }, []);

  async function loadMemories() {
    try {
      const data = await api.getMemories(50);
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    );
  }

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl font-bold text-white">Memories</h1>
          <p className="text-slate-400 mt-1 text-sm md:text-base">Things Zeke remembers.</p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-2 bg-blue-600 text-white px-3 py-2 md:px-4 rounded-lg hover:bg-blue-700 active:bg-blue-800 transition-colors flex-shrink-0"
        >
          <Plus className="w-5 h-5" />
          <span className="hidden md:inline">Add Memory</span>
        </button>
      </div>

      {showAddForm && (
        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Add New Memory</h2>
            <button
              onClick={() => setShowAddForm(false)}
              className="p-1 text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <form onSubmit={handleCreate} className="space-y-4">
            <textarea
              value={newMemory}
              onChange={(e) => setNewMemory(e.target.value)}
              placeholder="Enter something you want Zeke to remember..."
              className="w-full bg-slate-800 text-white rounded-lg px-4 py-3 border border-slate-600 focus:outline-none focus:border-blue-500 min-h-[100px] text-base"
              autoFocus
            />
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating || !newMemory.trim()}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {creating ? 'Saving...' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      <form onSubmit={handleSearch} className="flex gap-2 md:gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search memories..."
            className="w-full bg-slate-800 text-white rounded-lg pl-10 pr-4 py-3 border border-slate-600 focus:outline-none focus:border-blue-500 text-base"
          />
        </div>
        <button
          type="submit"
          disabled={isSearching || !searchQuery.trim()}
          className="bg-slate-700 text-white px-4 py-3 rounded-lg hover:bg-slate-600 active:bg-slate-500 transition-colors disabled:opacity-50"
        >
          {isSearching ? '...' : 'Search'}
        </button>
      </form>

      {searchResults.length > 0 && (
        <div className="bg-blue-900/30 border border-blue-700 rounded-xl p-4 md:p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base md:text-lg font-semibold text-blue-300">Search Results</h2>
            <button
              onClick={() => setSearchResults([])}
              className="text-blue-400 text-sm hover:underline"
            >
              Clear
            </button>
          </div>
          <ul className="space-y-3">
            {searchResults.map((result, index) => (
              <li key={index} className="p-3 bg-blue-900/50 rounded-lg text-blue-100 text-sm md:text-base">
                {result}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="bg-slate-900 rounded-xl border border-slate-700 divide-y divide-slate-700">
        {memories.length === 0 ? (
          <div className="p-8 md:p-12 text-center">
            <Brain className="w-10 h-10 md:w-12 md:h-12 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400">No memories yet.</p>
            <p className="text-slate-500 text-sm mt-2">
              Memories are extracted from your conversations.
            </p>
          </div>
        ) : (
          memories.map((memory) => (
            <div key={memory.id} className="p-4 flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-slate-200 text-sm md:text-base">{memory.content}</p>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <span className="text-xs text-slate-500">
                    {new Date(memory.created_at).toLocaleDateString()}
                  </span>
                  <span className="text-xs px-2 py-0.5 bg-slate-700 rounded text-slate-400">
                    {memory.category}
                  </span>
                  {memory.manually_added && (
                    <span className="text-xs px-2 py-0.5 bg-blue-900 rounded text-blue-300">
                      Manual
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleDelete(memory.id)}
                className="text-slate-500 hover:text-red-400 active:text-red-500 transition-colors p-1 flex-shrink-0"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
