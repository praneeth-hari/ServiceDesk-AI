import React, { useState, useEffect, useMemo } from 'react';
import {
  getHolidays,
  createHoliday,
  deleteHoliday,
  updateHoliday,
  type Holiday,
} from '../../api/holidays';
import {
  getWeekdayName,
  isWeekend,
  formatDateDisplay,
  filterHolidaysByYear,
  sortHolidaysAsc,
} from './holidayUtils';
import { DeleteHolidayModal } from './components/DeleteHolidayModal';
import { SlaNoteCard } from './components/SlaNoteCard';
import { getFriendlyErrorMessage } from '../../utils/errors';

export const HolidaysPage: React.FC = () => {
  // Current calendar year anchor
  const currentCalendarYear = useMemo(() => new Date().getFullYear(), []);
  const [selectedYear, setSelectedYear] = useState<number>(currentCalendarYear);
  const [reloadKey, setReloadKey] = useState<number>(0);

  // Data state
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Add holiday form state
  const [formDate, setFormDate] = useState<string>('');
  const [formName, setFormName] = useState<string>('');
  const [formSubmitting, setFormSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Inline edit state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDate, setEditDate] = useState<string>('');
  const [editName, setEditName] = useState<string>('');
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Delete modal state
  const [holidayToDelete, setHolidayToDelete] = useState<Holiday | null>(null);
  const [deleting, setDeleting] = useState<boolean>(false);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getHolidays(selectedYear);
        if (!ignore) {
          setHolidays(data);
          setFetchError(null);
        }
      } catch (err) {
        if (!ignore) {
          setFetchError(getFriendlyErrorMessage(err, 'Failed to load holidays'));
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    };

    load();
    return () => {
      ignore = true;
    };
  }, [selectedYear, reloadKey]);

  const handleRetry = () => {
    setLoading(true);
    setFetchError(null);
    setReloadKey((k) => k + 1);
  };

  const handleYearChange = (yr: number) => {
    setLoading(true);
    setSelectedYear(yr);
  };

  // Client-side guarantee: filter by year and sort ascending
  const displayedHolidays = useMemo(() => {
    const filtered = filterHolidaysByYear(holidays, selectedYear);
    return sortHolidaysAsc(filtered);
  }, [holidays, selectedYear]);

  // Handle Add Holiday
  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const trimmedName = formName.trim();
    if (!formDate || !trimmedName) return;

    // Check for duplicate date client-side first
    const isDuplicate = holidays.some((h) => h.holiday_date === formDate);
    if (isDuplicate) {
      setFormError(`A holiday on ${formDate} already exists`);
      return;
    }

    setFormSubmitting(true);
    try {
      const created = await createHoliday({
        holiday_date: formDate,
        name: trimmedName,
      });

      // Update holidays state
      setHolidays((prev) => sortHolidaysAsc([...prev, created]));

      // If added for a different year, automatically switch to that year
      const createdYear = parseInt(formDate.split('-')[0], 10);
      if (createdYear !== selectedYear) {
        setSelectedYear(createdYear);
      }

      // Reset form
      setFormDate('');
      setFormName('');
    } catch (err) {
      setFormError(getFriendlyErrorMessage(err));
    } finally {
      setFormSubmitting(false);
    }
  };

  // Start inline edit
  const handleStartEdit = (h: Holiday) => {
    setEditingId(h.id);
    setEditDate(h.holiday_date);
    setEditName(h.name);
    setEditError(null);
  };

  // Cancel inline edit
  const handleCancelEdit = () => {
    setEditingId(null);
    setEditDate('');
    setEditName('');
    setEditError(null);
  };

  // Save inline edit using PATCH
  const handleSaveEdit = async (id: number) => {
    setEditError(null);
    const trimmedName = editName.trim();
    if (!editDate || !trimmedName) return;

    // Check duplicate if date was changed
    const current = holidays.find((h) => h.id === id);
    if (current && editDate !== current.holiday_date) {
      const conflict = holidays.some(
        (h) => h.id !== id && h.holiday_date === editDate
      );
      if (conflict) {
        setEditError(`A holiday on ${editDate} already exists`);
        return;
      }
    }

    setEditSubmitting(true);
    try {
      const updated = await updateHoliday(id, {
        holiday_date: editDate,
        name: trimmedName,
      });

      setHolidays((prev) =>
        sortHolidaysAsc(prev.map((h) => (h.id === id ? updated : h)))
      );
      setEditingId(null);
    } catch (err) {
      setEditError(getFriendlyErrorMessage(err));
    } finally {
      setEditSubmitting(false);
    }
  };

  // Confirm delete
  const handleConfirmDelete = async () => {
    if (!holidayToDelete) return;
    setDeleting(true);
    try {
      await deleteHoliday(holidayToDelete.id);
      setHolidays((prev) => prev.filter((h) => h.id !== holidayToDelete.id));
      setHolidayToDelete(null);
    } catch (err) {
      setFetchError(getFriendlyErrorMessage(err, 'Failed to delete holiday'));
    } finally {
      setDeleting(false);
    }
  };

  // Year switcher options: previous year, current selected year, next year
  const yearOptions = [selectedYear - 1, selectedYear, selectedYear + 1];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-serif text-3xl font-bold tracking-tight text-ink">
          Holidays
        </h1>
        <p className="text-muted text-sm mt-1">
          Official public holidays observed by the organization. Excluded from business-hour SLAs.
        </p>
      </div>

      {/* Global Fetch Error / Retry Banner */}
      {fetchError && (
        <div
          role="alert"
          className="bg-coral/10 border border-coral/30 rounded-lg p-4 flex items-center justify-between gap-4 text-xs sm:text-sm text-coral"
        >
          <span>{fetchError}</span>
          <button
            type="button"
            onClick={handleRetry}
            className="px-3 py-1 bg-paper border border-coral/40 rounded text-coral font-medium hover:bg-paper2 transition-colors shrink-0"
          >
            Retry
          </button>
        </div>
      )}

      {/* 2-Column Responsive Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Left Card (2 columns wide on large screens) */}
        <div className="lg:col-span-2 bg-paper border border-line rounded-lg p-6 shadow-sm space-y-4">
          {/* Card Header: <year> holidays + count + Year switcher */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-line">
            <div className="flex items-center gap-3">
              <h2 className="font-serif text-xl font-semibold text-ink">
                {selectedYear} holidays
              </h2>
              {/* Hide count badge while loading or on fetch error */}
              {!loading && !fetchError && (
                <span
                  data-testid="holiday-count"
                  className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-paper2 text-ink border border-line"
                >
                  {displayedHolidays.length}
                </span>
              )}
            </div>

            {/* Year Switcher */}
            <div className="flex items-center gap-1 bg-paper2 rounded p-1 border border-line self-start sm:self-auto">
              {yearOptions.map((yr) => (
                <button
                  key={yr}
                  type="button"
                  onClick={() => handleYearChange(yr)}
                  className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                    selectedYear === yr
                      ? 'bg-teal text-paper font-semibold shadow-xs'
                      : 'text-muted hover:text-ink'
                  }`}
                  aria-label={`Show ${yr} holidays`}
                >
                  {yr}
                </button>
              ))}
            </div>
          </div>

          {/* Content Container: Loading skeleton / Empty / Table & Mobile Cards */}
          {loading ? (
            <div data-testid="holidays-loading-skeleton" className="space-y-3 py-6 animate-pulse">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-10 bg-paper2 rounded w-full" />
              ))}
            </div>
          ) : fetchError ? null : displayedHolidays.length === 0 ? (
            <div className="py-12 text-center text-muted">
              <p className="text-sm font-medium">
                No holidays for {selectedYear} yet. Add the first one.
              </p>
            </div>
          ) : (
            <>
              {/* Mobile View (< sm): Stacked cards, no horizontal scroll */}
              <div className="sm:hidden space-y-3">
                {displayedHolidays.map((h) => {
                  const isEditing = editingId === h.id;
                  const weekend = isWeekend(h.holiday_date);
                  const weekday = getWeekdayName(h.holiday_date);

                  if (isEditing) {
                    return (
                      <div
                        key={h.id}
                        className="p-3 bg-paper2/50 border border-teal/40 rounded-lg space-y-2.5"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="date"
                            value={editDate}
                            onChange={(e) => setEditDate(e.target.value)}
                            className="flex-1 px-2.5 py-1 text-xs rounded border border-line bg-paper text-ink focus:outline-none focus:ring-1 focus:ring-teal"
                            aria-label="Edit holiday date"
                          />
                          <span className="text-xs text-muted">
                            {editDate ? getWeekdayName(editDate) : '—'}
                          </span>
                        </div>
                        <div>
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            className="w-full px-2.5 py-1 text-xs rounded border border-line bg-paper text-ink focus:outline-none focus:ring-1 focus:ring-teal"
                            aria-label="Edit holiday name"
                          />
                          {editError && (
                            <p className="text-[11px] text-coral mt-1">
                              {editError}
                            </p>
                          )}
                        </div>
                        <div className="flex justify-end gap-2 pt-1">
                          <button
                            type="button"
                            onClick={handleCancelEdit}
                            disabled={editSubmitting}
                            className="px-2.5 py-1 text-xs font-medium rounded border border-line bg-paper text-muted hover:text-ink"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSaveEdit(h.id)}
                            disabled={
                              editSubmitting || !editDate || !editName.trim()
                            }
                            className="px-2.5 py-1 text-xs font-medium rounded bg-teal text-paper hover:bg-teal/90 disabled:opacity-50"
                          >
                            {editSubmitting ? 'Saving...' : 'Save'}
                          </button>
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div
                      key={h.id}
                      className="p-3 bg-paper border border-line/70 rounded-lg hover:border-line transition-colors space-y-1.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-serif text-sm font-semibold text-ink whitespace-nowrap">
                            {formatDateDisplay(h.holiday_date)}
                          </span>
                          <span className="text-xs text-muted">
                            ({weekday})
                          </span>
                          {weekend && (
                            <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-medium bg-paper2 text-muted border border-line">
                              weekend
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 shrink-0 pt-0.5">
                          <button
                            type="button"
                            onClick={() => handleStartEdit(h)}
                            className="text-xs text-muted hover:text-teal font-medium transition-colors"
                            aria-label={`Edit ${h.name}`}
                          >
                            Edit
                          </button>
                          <span className="text-line">|</span>
                          <button
                            type="button"
                            onClick={() => setHolidayToDelete(h)}
                            className="text-xs text-muted hover:text-coral font-medium transition-colors"
                            aria-label={`Delete ${h.name}`}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      <div className="text-sm text-ink font-medium">
                        {h.name}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Desktop View (>= sm): Table layout */}
              <div className="hidden sm:block overflow-x-auto">
                <table
                  className="w-full text-left text-xs sm:text-sm border-collapse"
                  aria-label={`${selectedYear} holidays table`}
                >
                  <thead>
                    <tr className="border-b border-line text-muted font-medium bg-paper2/50">
                      <th className="py-2.5 px-3">Date</th>
                      <th className="py-2.5 px-3">Day</th>
                      <th className="py-2.5 px-3">Name</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedHolidays.map((h) => {
                      const isEditing = editingId === h.id;
                      const weekend = isWeekend(h.holiday_date);
                      const weekday = getWeekdayName(h.holiday_date);

                      if (isEditing) {
                        return (
                          <tr
                            key={h.id}
                            className="border-b border-line bg-paper2/40"
                          >
                            <td className="py-2.5 px-3">
                              <input
                                type="date"
                                value={editDate}
                                onChange={(e) => setEditDate(e.target.value)}
                                className="px-2 py-1 text-xs rounded border border-line bg-paper text-ink focus:outline-none focus:ring-1 focus:ring-teal"
                                aria-label="Edit holiday date"
                              />
                            </td>
                            <td className="py-2.5 px-3 text-muted">
                              {editDate ? getWeekdayName(editDate) : '—'}
                            </td>
                            <td className="py-2.5 px-3">
                              <input
                                type="text"
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                className="w-full px-2 py-1 text-xs rounded border border-line bg-paper text-ink focus:outline-none focus:ring-1 focus:ring-teal"
                                aria-label="Edit holiday name"
                              />
                              {editError && (
                                <p className="text-[11px] text-coral mt-1">
                                  {editError}
                                </p>
                              )}
                            </td>
                            <td className="py-2.5 px-3 text-right space-x-2 whitespace-nowrap">
                              <button
                                type="button"
                                onClick={() => handleSaveEdit(h.id)}
                                disabled={
                                  editSubmitting ||
                                  !editDate ||
                                  !editName.trim()
                                }
                                className="px-2.5 py-1 text-xs font-medium rounded bg-teal text-paper hover:bg-teal/90 disabled:opacity-50"
                              >
                                {editSubmitting ? 'Saving...' : 'Save'}
                              </button>
                              <button
                                type="button"
                                onClick={handleCancelEdit}
                                disabled={editSubmitting}
                                className="px-2.5 py-1 text-xs font-medium rounded border border-line bg-paper text-muted hover:text-ink"
                              >
                                Cancel
                              </button>
                            </td>
                          </tr>
                        );
                      }

                      return (
                        <tr
                          key={h.id}
                          className="border-b border-line/60 hover:bg-paper2/30 transition-colors"
                        >
                          <td className="py-3 px-3 font-medium text-ink whitespace-nowrap">
                            {formatDateDisplay(h.holiday_date)}
                          </td>
                          <td className="py-3 px-3 text-muted whitespace-nowrap">
                            <span className="inline-flex items-center">
                              {weekday}
                              {weekend && (
                                <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-paper2 text-muted border border-line">
                                  weekend
                                </span>
                              )}
                            </span>
                          </td>
                          <td className="py-3 px-3 font-medium text-ink">
                            {h.name}
                          </td>
                          <td className="py-3 px-3 text-right space-x-2 whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() => handleStartEdit(h)}
                              className="text-xs text-muted hover:text-teal font-medium transition-colors"
                              aria-label={`Edit ${h.name}`}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => setHolidayToDelete(h)}
                              className="text-xs text-muted hover:text-coral font-medium transition-colors"
                              aria-label={`Delete ${h.name}`}
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        {/* Right Column (Form & SLA Card) */}
        <div className="space-y-6">
          {/* Add a holiday Form */}
          <div className="bg-paper border border-line rounded-lg p-5 shadow-sm space-y-4">
            <h3 className="font-serif text-base font-semibold text-ink">
              Add a holiday
            </h3>

            <form onSubmit={handleAddSubmit} className="space-y-3">
              <div>
                <label
                  htmlFor="holiday-date"
                  className="block text-xs font-medium text-muted uppercase tracking-wider mb-1"
                >
                  Date
                </label>
                <input
                  id="holiday-date"
                  type="date"
                  value={formDate}
                  onChange={(e) => {
                    setFormDate(e.target.value);
                    if (formError) setFormError(null);
                  }}
                  className="w-full px-3 py-2 text-xs sm:text-sm rounded border border-line bg-paper2/40 text-ink focus:outline-none focus:ring-1 focus:ring-teal"
                  required
                />
              </div>

              <div>
                <label
                  htmlFor="holiday-name"
                  className="block text-xs font-medium text-muted uppercase tracking-wider mb-1"
                >
                  Name
                </label>
                <input
                  id="holiday-name"
                  type="text"
                  placeholder="e.g. Diwali"
                  value={formName}
                  onChange={(e) => {
                    setFormName(e.target.value);
                    if (formError) setFormError(null);
                  }}
                  className="w-full px-3 py-2 text-xs sm:text-sm rounded border border-line bg-paper2/40 text-ink focus:outline-none focus:ring-1 focus:ring-teal"
                  required
                  maxLength={255}
                />
                {formError && (
                  <p
                    role="alert"
                    className="text-xs text-coral mt-1.5 font-medium"
                  >
                    {formError}
                  </p>
                )}
              </div>

              <button
                type="submit"
                disabled={
                  formSubmitting || !formDate || !formName.trim()
                }
                className="w-full py-2 px-4 rounded bg-teal text-paper text-xs sm:text-sm font-semibold hover:bg-teal/90 transition-colors shadow-xs disabled:opacity-50 disabled:cursor-not-allowed mt-2"
              >
                {formSubmitting ? 'Adding...' : 'Add holiday'}
              </button>
            </form>
          </div>

          {/* SLA Note Card */}
          <SlaNoteCard />
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <DeleteHolidayModal
        isOpen={holidayToDelete !== null}
        holiday={holidayToDelete}
        onConfirm={handleConfirmDelete}
        onCancel={() => setHolidayToDelete(null)}
        isDeleting={deleting}
      />
    </div>
  );
};
