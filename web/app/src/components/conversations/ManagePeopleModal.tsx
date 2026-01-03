'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Loader2, Pencil, Trash2, Plus, Check, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePeople } from '@/hooks/usePeople';
import type { Person } from '@/types/user';

interface ManagePeopleModalProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Modal for managing people (CRUD operations)
 */
export function ManagePeopleModal({ isOpen, onClose }: ManagePeopleModalProps) {
  const { people, loading, addPerson, updatePerson, removePerson } = usePeople();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newPersonName, setNewPersonName] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleStartEdit = (person: Person) => {
    setEditingId(person.id);
    setEditingName(person.name);
    setError(null);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditingName('');
  };

  const handleSaveEdit = async () => {
    if (!editingId || !editingName.trim()) return;

    // Check for duplicates
    const normalizedName = editingName.trim().toLowerCase();
    if (people.some((p) => p.id !== editingId && p.name.toLowerCase() === normalizedName)) {
      setError('A person with this name already exists');
      return;
    }

    setActionLoading(editingId);
    setError(null);

    const success = await updatePerson(editingId, editingName.trim());
    if (success) {
      handleCancelEdit();
    } else {
      setError('Failed to update name');
    }
    setActionLoading(null);
  };

  const handleCreatePerson = async () => {
    if (!newPersonName.trim()) return;

    // Check for duplicates
    const normalizedName = newPersonName.trim().toLowerCase();
    if (people.some((p) => p.name.toLowerCase() === normalizedName)) {
      setError('A person with this name already exists');
      return;
    }

    setActionLoading('new');
    setError(null);

    const newPerson = await addPerson(newPersonName.trim());
    if (newPerson) {
      setShowAddForm(false);
      setNewPersonName('');
    } else {
      setError('Failed to create person');
    }
    setActionLoading(null);
  };

  const handleDeletePerson = async (personId: string) => {
    setActionLoading(personId);
    setError(null);

    const success = await removePerson(personId);
    if (!success) {
      setError('Failed to delete person');
    }
    setDeleteConfirmId(null);
    setActionLoading(null);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/50 z-50"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className={cn(
              'fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50',
              'w-full max-w-md bg-bg-secondary rounded-2xl',
              'shadow-xl border border-bg-tertiary',
              'max-h-[85vh] overflow-hidden flex flex-col'
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-bg-tertiary">
              <div className="flex items-center gap-2">
                <User className="w-5 h-5 text-purple-primary" />
                <h2 className="text-lg font-semibold text-text-primary">Manage People</h2>
              </div>
              <button
                onClick={onClose}
                className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
              >
                <X className="w-5 h-5 text-text-tertiary" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {/* Error */}
              {error && (
                <div className="mb-4 p-3 rounded-lg bg-error/10 border border-error/20 text-error text-sm">
                  {error}
                </div>
              )}

              {/* Add Person Form */}
              {showAddForm ? (
                <div className="mb-4 p-3 rounded-lg bg-bg-tertiary border border-bg-quaternary">
                  <p className="text-sm font-medium text-text-primary mb-2">Add New Person</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newPersonName}
                      onChange={(e) => setNewPersonName(e.target.value)}
                      placeholder="Enter name..."
                      autoFocus
                      className={cn(
                        'flex-1 px-3 py-2 rounded-lg',
                        'bg-bg-secondary border border-bg-quaternary',
                        'text-sm text-text-primary placeholder:text-text-quaternary',
                        'focus:outline-none focus:ring-2 focus:ring-purple-primary/50'
                      )}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleCreatePerson();
                        if (e.key === 'Escape') {
                          setShowAddForm(false);
                          setNewPersonName('');
                        }
                      }}
                    />
                    <button
                      onClick={handleCreatePerson}
                      disabled={!newPersonName.trim() || actionLoading === 'new'}
                      className={cn(
                        'px-4 py-2 rounded-lg text-sm font-medium',
                        'bg-purple-primary hover:bg-purple-secondary text-white',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'transition-colors'
                      )}
                    >
                      {actionLoading === 'new' ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        'Add'
                      )}
                    </button>
                    <button
                      onClick={() => {
                        setShowAddForm(false);
                        setNewPersonName('');
                      }}
                      className="px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-quaternary transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowAddForm(true)}
                  className={cn(
                    'mb-4 w-full flex items-center justify-center gap-2 p-3 rounded-lg',
                    'border border-dashed border-bg-quaternary',
                    'text-sm font-medium text-text-tertiary',
                    'hover:bg-bg-tertiary hover:text-text-secondary hover:border-text-quaternary',
                    'transition-colors'
                  )}
                >
                  <Plus className="w-4 h-4" />
                  <span>Add Person</span>
                </button>
              )}

              {/* Loading */}
              {loading && (
                <div className="flex items-center justify-center gap-2 py-8 text-text-tertiary">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span className="text-sm">Loading people...</span>
                </div>
              )}

              {/* People List */}
              {!loading && people.length === 0 && (
                <div className="text-center py-8 text-text-tertiary">
                  <User className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p className="text-sm">No people added yet</p>
                  <p className="text-xs mt-1">Add people to tag speakers in transcripts</p>
                </div>
              )}

              {!loading && people.length > 0 && (
                <div className="space-y-2">
                  {people.map((person) => (
                    <div
                      key={person.id}
                      className={cn(
                        'flex items-center gap-3 p-3 rounded-lg',
                        'bg-bg-tertiary border border-bg-quaternary'
                      )}
                    >
                      {/* Avatar */}
                      <div className="w-10 h-10 rounded-full bg-purple-primary/20 flex items-center justify-center text-purple-primary font-medium">
                        {person.name.charAt(0).toUpperCase()}
                      </div>

                      {/* Name or Edit Input */}
                      {editingId === person.id ? (
                        <input
                          type="text"
                          value={editingName}
                          onChange={(e) => setEditingName(e.target.value)}
                          autoFocus
                          className={cn(
                            'flex-1 px-3 py-1.5 rounded-lg',
                            'bg-bg-secondary border border-purple-primary',
                            'text-sm text-text-primary',
                            'focus:outline-none'
                          )}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSaveEdit();
                            if (e.key === 'Escape') handleCancelEdit();
                          }}
                        />
                      ) : (
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-text-primary truncate">
                            {person.name}
                          </p>
                          {person.speech_samples_count > 0 && (
                            <p className="text-xs text-text-tertiary">
                              {person.speech_samples_count} speech sample
                              {person.speech_samples_count !== 1 ? 's' : ''}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Actions */}
                      {editingId === person.id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={handleSaveEdit}
                            disabled={!editingName.trim() || actionLoading === person.id}
                            className={cn(
                              'p-2 rounded-lg transition-colors',
                              'text-success hover:bg-success/10',
                              'disabled:opacity-50'
                            )}
                          >
                            {actionLoading === person.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Check className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={handleCancelEdit}
                            className="p-2 rounded-lg text-text-tertiary hover:bg-bg-quaternary transition-colors"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ) : deleteConfirmId === person.id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDeletePerson(person.id)}
                            disabled={actionLoading === person.id}
                            className={cn(
                              'px-3 py-1.5 rounded-lg text-xs font-medium',
                              'bg-error/20 text-error hover:bg-error/30',
                              'transition-colors'
                            )}
                          >
                            {actionLoading === person.id ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              'Delete'
                            )}
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="px-3 py-1.5 rounded-lg text-xs text-text-secondary hover:bg-bg-quaternary transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleStartEdit(person)}
                            className="p-2 rounded-lg text-text-tertiary hover:text-text-secondary hover:bg-bg-quaternary transition-colors"
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(person.id)}
                            className="p-2 rounded-lg text-text-tertiary hover:text-error hover:bg-error/10 transition-colors"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-bg-tertiary">
              <button
                onClick={onClose}
                className={cn(
                  'w-full px-4 py-2.5 rounded-xl',
                  'text-sm font-medium',
                  'bg-bg-tertiary hover:bg-bg-quaternary text-text-primary',
                  'transition-colors'
                )}
              >
                Done
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
