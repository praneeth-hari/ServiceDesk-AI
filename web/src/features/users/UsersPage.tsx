import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/useAuth';
import type { UserAdmin, UserRole } from '../../api/types';
import { listAdminUsers, updateUserRole, updateUserStatus } from '../../api/users';
import { ApiError } from '../../api/client';
import { AddUserModal } from './components/AddUserModal';
import { DeactivateUserModal } from './components/DeactivateUserModal';

export const UsersPage: React.FC = () => {
  const { user: currentUser } = useAuth();

  const [users, setUsers] = useState<UserAdmin[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [activeCount, setActiveCount] = useState<number>(0);

  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const [isLoading, setIsLoading] = useState(true);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Modals state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [deactivatingUser, setDeactivatingUser] = useState<UserAdmin | null>(null);
  const [isDeactivating, setIsDeactivating] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  // Role change pending tracking: userId currently updating
  const [roleUpdatingId, setRoleUpdatingId] = useState<number | null>(null);

  useEffect(() => {
    let ignore = false;

    const loadUsers = async () => {
      try {
        const res = await listAdminUsers({
          q: searchTerm.trim() || undefined,
          role: roleFilter !== 'all' ? (roleFilter as UserRole) : undefined,
          is_active: statusFilter === 'all' ? undefined : statusFilter === 'active',
        });
        if (!ignore) {
          const items = res.rows ?? res.users ?? [];
          const active = res.active_count ?? res.active ?? 0;
          setUsers(items);
          setTotalCount(res.total);
          setActiveCount(active);
          setErrorBanner(null);
        }
      } catch (err) {
        if (!ignore) {
          if (err instanceof ApiError) {
            setErrorBanner(err.message);
          } else {
            setErrorBanner('Failed to load users. Please refresh the page.');
          }
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    };

    loadUsers();

    return () => {
      ignore = true;
    };
  }, [searchTerm, roleFilter, statusFilter, refreshTrigger]);

  const triggerRefresh = () => {
    setIsLoading(true);
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleRoleChange = async (targetUser: UserAdmin, newRole: UserRole) => {
    if (targetUser.role === newRole) return;
    setErrorBanner(null);
    setRoleUpdatingId(targetUser.id);

    try {
      await updateUserRole(targetUser.id, newRole);
      setUsers((prev) =>
        prev.map((u) => (u.id === targetUser.id ? { ...u, role: newRole } : u))
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorBanner(err.message);
      } else {
        setErrorBanner('Failed to update role');
      }
      // Revert select dropdown by forcing state refresh
      setUsers((prev) => [...prev]);
    } finally {
      setRoleUpdatingId(null);
    }
  };

  const handleConfirmDeactivate = async () => {
    if (!deactivatingUser) return;
    setIsDeactivating(true);
    setDeactivateError(null);
    try {
      await updateUserStatus(deactivatingUser.id, false);
      setDeactivatingUser(null);
      triggerRefresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setDeactivateError(err.message);
      } else {
        setDeactivateError('Failed to deactivate user');
      }
    } finally {
      setIsDeactivating(false);
    }
  };

  const handleReactivate = async (targetUser: UserAdmin) => {
    setErrorBanner(null);
    try {
      await updateUserStatus(targetUser.id, true);
      triggerRefresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorBanner(err.message);
      } else {
        setErrorBanner('Failed to reactivate user');
      }
    }
  };

  const getInitials = (name: string, email: string) => {
    const clean = name.trim() || email.trim();
    const parts = clean.split(' ').filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return clean.slice(0, 2).toUpperCase();
  };

  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-line">
        <div>
          <h1 className="font-serif text-3xl font-bold tracking-tight text-ink">
            Users
          </h1>
          <p className="text-sm text-muted mt-1">
            Manage who can sign in and what they can do.{' '}
            <span className="font-semibold text-ink">
              {totalCount} {totalCount === 1 ? 'user' : 'users'}
            </span>{' '}
            ·{' '}
            <span className="font-semibold text-ink">
              {activeCount} active
            </span>
            .
          </p>
        </div>
        <div>
          <button
            type="button"
            onClick={() => setIsAddModalOpen(true)}
            className="inline-flex items-center px-4 py-2 bg-teal text-white text-sm font-medium rounded hover:bg-teal-dark transition-colors shadow-xs"
          >
            + Add user
          </button>
        </div>
      </div>

      {/* Global Error Banner */}
      {errorBanner && (
        <div
          role="alert"
          className="bg-coral/10 border border-coral/30 rounded p-4 text-sm text-coral font-medium flex justify-between items-center"
        >
          <span>{errorBanner}</span>
          <button
            type="button"
            onClick={() => setErrorBanner(null)}
            className="text-coral hover:text-ink font-bold ml-4"
          >
            &times;
          </button>
        </div>
      )}

      {/* Filters Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="flex-1 max-w-md">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => {
              setIsLoading(true);
              setSearchTerm(e.target.value);
            }}
            placeholder="Search by name or email..."
            aria-label="Search users"
            className="w-full px-3 py-2 text-sm bg-paper border border-line rounded focus:outline-hidden focus:border-teal text-ink placeholder:text-muted/60"
          />
        </div>
        <div className="flex items-center gap-3">
          <div>
            <label htmlFor="filter-role" className="sr-only">
              Filter by role
            </label>
            <select
              id="filter-role"
              value={roleFilter}
              onChange={(e) => {
                setIsLoading(true);
                setRoleFilter(e.target.value);
              }}
              className="px-3 py-2 text-sm bg-paper border border-line rounded focus:outline-hidden focus:border-teal text-ink"
            >
              <option value="all">All roles</option>
              <option value="admin">Admin</option>
              <option value="agent">Agent</option>
              <option value="requester">Requester</option>
            </select>
          </div>
          <div>
            <label htmlFor="filter-status" className="sr-only">
              Filter by status
            </label>
            <select
              id="filter-status"
              value={statusFilter}
              onChange={(e) => {
                setIsLoading(true);
                setStatusFilter(e.target.value);
              }}
              className="px-3 py-2 text-sm bg-paper border border-line rounded focus:outline-hidden focus:border-teal text-ink"
            >
              <option value="all">All status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>
      </div>

      {/* Users Table */}
      <div className="border border-line rounded-lg overflow-hidden bg-paper shadow-xs">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-left text-sm">
            <thead className="bg-paper2 text-xs font-semibold uppercase tracking-wider text-muted">
              <tr>
                <th scope="col" className="px-6 py-3">
                  User
                </th>
                <th scope="col" className="px-6 py-3">
                  Role
                </th>
                <th scope="col" className="px-6 py-3">
                  Status
                </th>
                <th scope="col" className="px-6 py-3">
                  Created
                </th>
                <th scope="col" className="px-6 py-3 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-paper">
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted animate-pulse">
                    Loading users...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted">
                    No users match your filters.
                  </td>
                </tr>
              ) : (
                users.map((u) => {
                  const isCurrent = currentUser?.id === u.id;
                  const isRowUpdating = roleUpdatingId === u.id;

                  return (
                    <tr
                      key={u.id}
                      className={`hover:bg-paper2/40 transition-colors ${
                        !u.is_active ? 'opacity-60 bg-paper2/30' : ''
                      }`}
                    >
                      {/* User Info */}
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center space-x-3">
                          <div className="w-8 h-8 rounded-full bg-paper2 border border-line flex items-center justify-center font-bold text-xs text-ink shrink-0">
                            {getInitials(u.full_name, u.email)}
                          </div>
                          <div>
                            <div className="flex items-center space-x-2">
                              <span className="font-medium text-ink">{u.full_name}</span>
                              {isCurrent && (
                                <span
                                  className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-paper2 text-ink border border-line"
                                  title="Signed in account"
                                >
                                  YOU
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-muted">{u.email}</div>
                          </div>
                        </div>
                      </td>

                      {/* Role Dropdown */}
                      <td className="px-6 py-4 whitespace-nowrap">
                        <select
                          value={u.role}
                          disabled={isCurrent || isRowUpdating}
                          onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
                          title={
                            isCurrent
                              ? 'Your own row is locked so you cannot demote yourself'
                              : 'Change role'
                          }
                          aria-label={`Role for ${u.full_name}`}
                          className="px-2.5 py-1 text-xs font-medium bg-paper border border-line rounded capitalize text-ink focus:outline-hidden focus:border-teal disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <option value="requester">Requester</option>
                          <option value="agent">Agent</option>
                          <option value="admin">Admin</option>
                        </select>
                      </td>

                      {/* Status Pill */}
                      <td className="px-6 py-4 whitespace-nowrap">
                        {u.is_active ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-paper2 text-muted border border-line">
                            Inactive
                          </span>
                        )}
                      </td>

                      {/* Created Date */}
                      <td className="px-6 py-4 whitespace-nowrap text-xs text-muted">
                        {formatDate(u.created_at)}
                      </td>

                      {/* Actions */}
                      <td className="px-6 py-4 whitespace-nowrap text-right">
                        {isCurrent ? (
                          <button
                            type="button"
                            disabled
                            title="Your own row is locked so you cannot deactivate yourself"
                            className="text-xs font-medium text-muted/50 cursor-not-allowed px-2 py-1"
                          >
                            Deactivate
                          </button>
                        ) : u.is_active ? (
                          <button
                            type="button"
                            onClick={() => {
                              setDeactivateError(null);
                              setDeactivatingUser(u);
                            }}
                            className="text-xs font-medium text-coral hover:text-coral-dark px-2 py-1 transition-colors"
                          >
                            Deactivate
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleReactivate(u)}
                            className="text-xs font-medium text-teal hover:text-teal-dark px-2 py-1 transition-colors"
                          >
                            Reactivate
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Safety Footer Note */}
      <div className="bg-paper2 border border-line rounded p-4 text-xs text-muted leading-relaxed">
        <strong>Notice:</strong> Your own row is locked so you cannot demote or deactivate
        yourself. The last active admin can never be demoted or deactivated. Role and status
        changes are recorded.
      </div>

      {/* Add User Modal */}
      <AddUserModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSuccess={triggerRefresh}
      />

      {/* Deactivate User Modal */}
      <DeactivateUserModal
        isOpen={Boolean(deactivatingUser)}
        user={deactivatingUser}
        onConfirm={handleConfirmDeactivate}
        onCancel={() => setDeactivatingUser(null)}
        isDeactivating={isDeactivating}
        errorMessage={deactivateError}
      />
    </div>
  );
};
