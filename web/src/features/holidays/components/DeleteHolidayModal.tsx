import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { Holiday } from '../../../api/holidays';

export interface DeleteHolidayModalProps {
  isOpen: boolean;
  holiday: Holiday | null;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}

export const DeleteHolidayModal: React.FC<DeleteHolidayModalProps> = ({
  isOpen,
  holiday,
  onConfirm,
  onCancel,
  isDeleting,
}) => {
  const cancelBtnRef = useRef<HTMLButtonElement | null>(null);
  const deleteBtnRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      cancelBtnRef.current?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
        return;
      }

      // Trap focus between Cancel and Delete
      if (e.key === 'Tab') {
        const focusable = [cancelBtnRef.current, deleteBtnRef.current].filter(
          Boolean
        ) as HTMLElement[];
        if (focusable.length < 2) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen || !holiday) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 m-0 p-4 flex items-center justify-center bg-ink/60 backdrop-blur-xs"
      onClick={onCancel}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-dialog-title"
        className="w-full max-w-md bg-paper border border-line rounded-lg shadow-xl p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-full bg-coral/10 text-coral shrink-0">
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </div>
          <div>
            <h3
              id="delete-dialog-title"
              className="text-base font-semibold text-ink font-serif"
            >
              Delete {holiday.name} ({holiday.holiday_date})?
            </h3>
            <p className="text-xs sm:text-sm text-muted mt-1.5 leading-relaxed">
              Are you sure you want to delete this public holiday? Applies to tickets created or re-timed after this change; existing due dates are not recalculated. This action cannot be undone.
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-line">
          <button
            ref={cancelBtnRef}
            type="button"
            onClick={onCancel}
            disabled={isDeleting}
            className="px-3 py-1.5 text-xs font-medium rounded border border-line bg-paper2/50 text-ink hover:bg-paper2 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            ref={deleteBtnRef}
            type="button"
            onClick={onConfirm}
            disabled={isDeleting}
            className="px-3 py-1.5 text-xs font-medium rounded bg-coral text-paper hover:bg-coral/90 transition-colors shadow-xs disabled:opacity-50"
          >
            {isDeleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
