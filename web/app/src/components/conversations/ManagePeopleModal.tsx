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
    if (
      people.some((p) => p.id !== editingId && p.name.toLowerCase() === normalizedName)
    ) {
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
            className="fixed inset-0 z-50 bg-black/50"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className={cn(
              'fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2',
              'w-full max-w-md rounded-2xl bg-bg-secondary',
              'border border-bg-tertiary shadow-xl',
              'flex max-h-[85vh] flex-col overflow-hidden',
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-bg-tertiary p-4">
              <div className="flex items-center gap-2">
                <User className="h-5 w-5 text-text-primary" />
                <h2 className="text-lg font-semibold text-text-primary">Manage People</h2>
              </div>
              <button
                onClick={onClose}
                className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5 text-text-tertiary" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {/* Error */}
              {error && (
                <div className="mb-4 rounded-lg border border-error/20 bg-error/10 p-3 text-sm text-error">
                  {error}
                </div>
              )}

              {/* Add Person Form */}
              {showAddForm ? (
                <div className="mb-4 rounded-lg border border-bg-quaternary bg-bg-tertiary p-3">
                  <p className="mb-2 text-sm font-medium text-text-primary">
                    Add New Person
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newPersonName}
                      onChange={(e) => setNewPersonName(e.target.value)}
                      placeholder="Enter name..."
                      autoFocus
                      className={cn(
                        'flex-1 rounded-lg px-3 py-2',
                        'border border-bg-quaternary bg-bg-secondary',
                        'text-sm text-text-primary placeholder:text-text-quaternary',
                        'focus:outline-none focus:ring-2 focus:ring-white/25',
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
                        'rounded-lg px-4 py-2 text-sm font-medium',
                        'bg-text-primary text-bg-primary hover:bg-text-primary/90',
                        'disabled:cursor-not-allowed disabled:opacity-50',
                        'transition-colors',
                      )}
                    >
                      {actionLoading === 'new' ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        'Add'
                      )}
                    </button>
                    <button
                      onClick={() => {
                        setShowAddForm(false);
                        setNewPersonName('');
                      }}
                      className="rounded-lg px-3 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-quaternary"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowAddForm(true)}
                  className={cn(
                    'mb-4 flex w-full items-center justify-center gap-2 rounded-lg p-3',
                    'border border-dashed border-bg-quaternary',
                    'text-sm font-medium text-text-tertiary',
                    'hover:border-text-quaternary hover:bg-bg-tertiary hover:text-text-secondary',
                    'transition-colors',
                  )}
                >
                  <Plus className="h-4 w-4" />
                  <span>Add Person</span>
                </button>
              )}

              {/* Loading */}
              {loading && (
                <div className="flex items-center justify-center gap-2 py-8 text-text-tertiary">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span className="text-sm">Loading people...</span>
                </div>
              )}

              {/* People List */}
              {!loading && people.length === 0 && (
                <div className="py-8 text-center text-text-tertiary">
                  <User className="mx-auto mb-3 h-12 w-12 opacity-50" />
                  <p className="text-sm">No people added yet</p>
                  <p className="mt-1 text-xs">
                    Add people to tag speakers in transcripts
                  </p>
                </div>
              )}

              {!loading && people.length > 0 && (
                <div className="space-y-2">
                  {people.map((person) => (
                    <div
                      key={person.id}
                      className={cn(
                        'flex items-center gap-3 rounded-lg p-3',
                        'border border-bg-quaternary bg-bg-tertiary',
                      )}
                    >
                      {/* Avatar */}
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/[0.14] font-medium text-text-primary">
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
                            'flex-1 rounded-lg px-3 py-1.5',
                            'border border-white/25 bg-bg-secondary',
                            'text-sm text-text-primary',
                            'focus:outline-none',
                          )}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSaveEdit();
                            if (e.key === 'Escape') handleCancelEdit();
                          }}
                        />
                      ) : (
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-text-primary">
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
                              'rounded-lg p-2 transition-colors',
                              'text-success hover:bg-success/10',
                              'disabled:opacity-50',
                            )}
                          >
                            {actionLoading === person.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Check className="h-4 w-4" />
                            )}
                          </button>
                          <button
                            onClick={handleCancelEdit}
                            className="rounded-lg p-2 text-text-tertiary transition-colors hover:bg-bg-quaternary"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ) : deleteConfirmId === person.id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDeletePerson(person.id)}
                            disabled={actionLoading === person.id}
                            className={cn(
                              'rounded-lg px-3 py-1.5 text-xs font-medium',
                              'bg-error/20 text-error hover:bg-error/30',
                              'transition-colors',
                            )}
                          >
                            {actionLoading === person.id ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              'Delete'
                            )}
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="rounded-lg px-3 py-1.5 text-xs text-text-secondary transition-colors hover:bg-bg-quaternary"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleStartEdit(person)}
                            className="rounded-lg p-2 text-text-tertiary transition-colors hover:bg-bg-quaternary hover:text-text-secondary"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(person.id)}
                            className="rounded-lg p-2 text-text-tertiary transition-colors hover:bg-error/10 hover:text-error"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-bg-tertiary p-4">
              <button
                onClick={onClose}
                className={cn(
                  'w-full rounded-xl px-4 py-2.5',
                  'text-sm font-medium',
                  'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary',
                  'transition-colors',
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
