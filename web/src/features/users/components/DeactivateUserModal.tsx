import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { UserAdmin } from '../../../api/types';

export interface DeactivateUserModalProps {
  isOpen: boolean;
  user: UserAdmin | null;
  onConfirm: () => void;
  onCancel: () => void;
  isDeactivating: boolean;
  errorMessage?: string | null;
}

export const DeactivateUserModal: React.FC<DeactivateUserModalProps> = ({
  isOpen,
  user,
  onConfirm,
  onCancel,
  isDeactivating,
  errorMessage,
}) => {
  const cancelBtnRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        cancelBtnRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen || !user) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 m-0 p-4 flex items-center justify-center bg-ink/60 backdrop-blur-xs"
      onClick={onCancel}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="deactivate-dialog-title"
        className="w-full max-w-md bg-paper border border-line rounded-lg shadow-xl p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center pb-2 border-b border-line">
          <h2 id="deactivate-dialog-title" className="font-serif text-xl font-bold text-ink">
            Deactivate {user.full_name}?
          </h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close dialog"
            className="text-muted hover:text-ink text-lg leading-none"
          >
            &times;
          </button>
        </div>

        {errorMessage && (
          <div
            role="alert"
            className="bg-coral/10 border border-coral/30 rounded p-3 text-xs text-coral font-medium"
          >
            {errorMessage}
          </div>
        )}

        <div className="space-y-3 text-sm text-ink leading-relaxed">
          <p>
            When deactivated, <strong>{user.full_name}</strong> will no longer be able to sign in
            to Runway. Their existing sessions and access tokens will stop working immediately.
          </p>
          <p className="text-xs text-muted">
            All tickets, comments, status changes, and activity history authored by them will stay
            safely in the system. The account can be reactivated by an admin at any time.
          </p>

          {user.open_assigned_count > 0 && (
            <div
              role="note"
              className="bg-amber-500/10 border border-amber-500/30 rounded p-3 text-xs text-amber-800 space-y-1 font-medium"
            >
              <div className="font-bold flex items-center space-x-1">
                <span>Warning: Assigned Tickets</span>
              </div>
              <p>
                {user.full_name} has {user.open_assigned_count}{' '}
                {user.open_assigned_count === 1 ? 'open ticket' : 'open tickets'} assigned to them.
                They will stay assigned until you reassign them.
              </p>
            </div>
          )}
        </div>

        <div className="flex justify-end space-x-3 pt-3 border-t border-line">
          <button
            ref={cancelBtnRef}
            type="button"
            onClick={onCancel}
            disabled={isDeactivating}
            className="px-4 py-2 text-sm font-medium border border-line rounded text-muted hover:text-ink hover:bg-paper2 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isDeactivating}
            className="px-4 py-2 text-sm font-medium bg-coral text-white rounded hover:bg-coral-dark transition-colors disabled:opacity-50"
          >
            {isDeactivating ? 'Deactivating...' : 'Deactivate'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

