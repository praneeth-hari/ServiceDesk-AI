import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { UserRole } from '../../../api/types';
import { createAdminUser } from '../../../api/users';
import { ApiError } from '../../../api/client';

export interface AddUserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const AddUserModal: React.FC<AddUserModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<UserRole>('requester');
  const [password, setPassword] = useState('');

  const [formErrors, setFormErrors] = useState<{ [key: string]: string }>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nameInputRef = useRef<HTMLInputElement | null>(null);
  const cancelBtnRef = useRef<HTMLButtonElement | null>(null);

  const resetForm = useCallback(() => {
    setFullName('');
    setEmail('');
    setRole('requester');
    setPassword('');
    setFormErrors({});
    setServerError(null);
    setIsSubmitting(false);
  }, []);

  const handleClose = useCallback(() => {
    resetForm();
    onClose();
  }, [resetForm, onClose]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        nameInputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        handleClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, handleClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);

    const errors: { [key: string]: string } = {};
    if (!fullName.trim()) {
      errors.fullName = 'Full name is required';
    }
    if (!email.trim()) {
      errors.email = 'Email address is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = 'Please enter a valid email address';
    }
    if (!password) {
      errors.password = 'Password is required';
    } else if (password.length < 8) {
      errors.password = 'Password must be at least 8 characters';
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    setIsSubmitting(true);
    try {
      await createAdminUser({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        role,
        password,
      });
      resetForm();
      onSuccess();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setServerError('Email already in use. Please use a different address.');
        } else {
          setServerError(err.message || 'Failed to create user');
        }
      } else {
        setServerError('Network error while creating user');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 m-0 p-4 flex items-center justify-center bg-ink/60 backdrop-blur-xs"
      onClick={handleClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-user-dialog-title"
        className="w-full max-w-md bg-paper border border-line rounded-lg shadow-xl p-6 space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center pb-2 border-b border-line">
          <h2 id="add-user-dialog-title" className="font-serif text-xl font-bold text-ink">
            Add user
          </h2>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close dialog"
            className="text-muted hover:text-ink text-lg leading-none"
          >
            &times;
          </button>
        </div>

        {serverError && (
          <div
            role="alert"
            className="bg-coral/10 border border-coral/30 rounded p-3 text-xs text-coral font-medium"
          >
            {serverError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="add-user-name" className="block text-xs font-semibold text-ink mb-1">
              Full name
            </label>
            <input
              id="add-user-name"
              ref={nameInputRef}
              type="text"
              value={fullName}
              onChange={(e) => {
                setFullName(e.target.value);
                if (formErrors.fullName) setFormErrors((prev) => ({ ...prev, fullName: '' }));
              }}
              placeholder="e.g. Jane Doe"
              className="w-full px-3 py-2 text-sm bg-paper border border-line rounded focus:outline-hidden focus:border-teal text-ink placeholder:text-muted/60"
            />
            {formErrors.fullName && (
              <p className="text-xs text-coral mt-1">{formErrors.fullName}</p>
            )}
          </div>

          <div>
            <label htmlFor="add-user-email" className="block text-xs font-semibold text-ink mb-1">
              Email
            </label>
            <input
              id="add-user-email"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (formErrors.email) setFormErrors((prev) => ({ ...prev, email: '' }));
                if (serverError) setServerError(null);
              }}
              placeholder="e.g. jane@example.com"
              className="w-full px-3 py-2 text-sm bg-paper border border-line rounded focus:outline-hidden focus:border-teal text-ink placeholder:text-muted/60"
            />
            {formErrors.email && (
              <p className="text-xs text-coral mt-1">{formErrors.email}</p>
            )}
          </div>

          <div>
            <label htmlFor="add-user-role" className="block text-xs font-semibold text-ink mb-1">
              Role
            </label>
            <select
              id="add-user-role"
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              className="w-full px-3 py-2 text-sm bg-paper border border-line rounded focus:outline-hidden focus:border-teal text-ink capitalize"
            >
              <option value="requester">Requester</option>
              <option value="agent">Agent</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          <div>
            <label htmlFor="add-user-password" className="block text-xs font-semibold text-ink mb-1">
              Password (at least 8 characters)
            </label>
            <input
              id="add-user-password"
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (formErrors.password) setFormErrors((prev) => ({ ...prev, password: '' }));
              }}
              placeholder="••••••••"
              className="w-full px-3 py-2 text-sm bg-paper border border-line rounded focus:outline-hidden focus:border-teal text-ink placeholder:text-muted/60"
            />
            {formErrors.password && (
              <p className="text-xs text-coral mt-1">{formErrors.password}</p>
            )}
          </div>

          <div className="flex justify-end space-x-3 pt-3 border-t border-line">
            <button
              ref={cancelBtnRef}
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-sm font-medium border border-line rounded text-muted hover:text-ink hover:bg-paper2 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-medium bg-teal text-white rounded hover:bg-teal-dark transition-colors disabled:opacity-50"
            >
              {isSubmitting ? 'Creating...' : 'Create user'}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
};
