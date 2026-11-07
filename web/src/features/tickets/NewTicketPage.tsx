import React, { useState, useEffect, useRef, useId, useContext } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { createTicket } from '../../api/tickets';
import { suggestTriage } from '../../api/triage';
import type {
  TicketCategory,
  TicketPriority,
  TriageSuggestResponse,
} from '../../api/types';
import { ApiError } from '../../api/client';
import { AuthContext } from '../../context/auth-context';
import { StatusBadge, PriorityBadge } from './components/Badges';
import { formatRelativeTime } from './ticketDetailHelpers';
import {
  TRIAGE_BENCHMARKS,
  TRIAGE_HONESTY_SUMMARY,
  TRIAGE_EXPLANATION,
} from './triageConstants';

const CATEGORY_OPTIONS: { value: TicketCategory; label: string }[] = [
  { value: 'network', label: 'Network' },
  { value: 'hardware', label: 'Hardware' },
  { value: 'software', label: 'Software' },
  { value: 'access', label: 'Access & Accounts' },
  { value: 'email', label: 'Email' },
  { value: 'other', label: 'Other' },
];

const PRIORITY_OPTIONS: { value: TicketPriority; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
];

export const NewTicketPage: React.FC = () => {
  const navigate = useNavigate();

  // Form State
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<TicketCategory | ''>('');
  const [priority, setPriority] = useState<TicketPriority>('medium');

  const [fieldErrors, setFieldErrors] = useState<{ [key: string]: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Triage Suggestion State
  const [triageResult, setTriageResult] = useState<TriageSuggestResponse | null>(null);
  const [triageLoading, setTriageLoading] = useState(false);
  const [triageUnavailable, setTriageUnavailable] = useState(false);
  const [appliedCategory, setAppliedCategory] = useState(false);
  const [appliedPriority, setAppliedPriority] = useState(false);

  // Duplicate candidate state
  const [dismissedDuplicateIds, setDismissedDuplicateIds] = useState<number[]>([]);

  // Honesty note expanded state
  const [showAccuracy, setShowAccuracy] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const titleInputId = useId();
  const descInputId = useId();
  const catInputId = useId();
  const prioInputId = useId();

  const authContext = useContext(AuthContext);
  const isRequester = authContext?.user?.role === 'requester';

  const possibleDuplicates = triageResult?.possible_duplicates ?? [];
  const activeDuplicates = possibleDuplicates.filter(
    (dup) => !dismissedDuplicateIds.includes(dup.id)
  );
  const isDuplicateDismissed =
    possibleDuplicates.length > 0 && activeDuplicates.length === 0;

  // Debounced Triage Suggestion Effect
  useEffect(() => {
    const trimmedTitle = title.trim();
    const trimmedDesc = description.trim();
    const combinedLength = trimmedTitle.length + trimmedDesc.length;

    // Do not call suggest API until BOTH title and description are non-empty
    if (
      trimmedTitle.length === 0 ||
      trimmedDesc.length === 0 ||
      combinedLength < TRIAGE_BENCHMARKS.minTextLength
    ) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      const resetTimer = setTimeout(() => {
        setTriageResult(null);
        setTriageLoading(false);
        setTriageUnavailable(false);
      }, 0);
      return () => {
        clearTimeout(resetTimer);
      };
    }

    const timer = setTimeout(async () => {
      setTriageLoading(true);
      setTriageUnavailable(false);

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const response = await suggestTriage(
          {
            title: trimmedTitle,
            description: trimmedDesc,
          },
          controller.signal
        );

        if (!controller.signal.aborted) {
          setTriageResult(response);
          setTriageLoading(false);
          setTriageUnavailable(false);
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          return;
        }
        if (!controller.signal.aborted) {
          setTriageLoading(false);
          setTriageUnavailable(true);
        }
      }
    }, TRIAGE_BENCHMARKS.debounceMs);

    return () => {
      clearTimeout(timer);
    };
  }, [title, description]);

  // Handlers for suggestions
  const handleApplyCategory = (cat: TicketCategory) => {
    setCategory(cat);
    setAppliedCategory(true);
    setFieldErrors((prev) => {
      const copy = { ...prev };
      delete copy.category;
      return copy;
    });
  };

  const handleApplyPriority = (prio: TicketPriority) => {
    setPriority(prio);
    setAppliedPriority(true);
  };

  // Form submit handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Client-side validation
    const errors: { [key: string]: string } = {};
    if (!title.trim()) {
      errors.title = 'Title is required.';
    } else if (title.trim().length > 255) {
      errors.title = 'Title must be 255 characters or fewer.';
    }

    if (!description.trim()) {
      errors.description = 'Description is required.';
    }

    if (!category) {
      errors.category = 'Please choose a category.';
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setSubmitting(true);

    try {
      const triage_suggestion =
        triageResult && triageResult.suggested_category && triageResult.suggested_priority
          ? {
              suggested_category: triageResult.suggested_category,
              suggested_priority: triageResult.suggested_priority,
              method: triageResult.method || 'knn',
              embedder: triageResult.embedder || null,
            }
          : undefined;

      const created = await createTicket({
        title: title.trim(),
        description: description.trim(),
        category: category as TicketCategory,
        priority,
        ...(triage_suggestion ? { triage_suggestion } : {}),
      });
      navigate(`/tickets/${created.id}`);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 422) {
        const msg = err.message || '';
        const newFieldErrors: { [key: string]: string } = {};
        const parts = msg.split(';');
        for (const part of parts) {
          const trimmed = part.trim();
          if (/title/i.test(trimmed)) {
            newFieldErrors.title = trimmed.replace(/^body\.\w+:\s*/, '');
          } else if (/description/i.test(trimmed)) {
            newFieldErrors.description = trimmed.replace(/^body\.\w+:\s*/, '');
          } else if (/category/i.test(trimmed)) {
            newFieldErrors.category = trimmed.replace(/^body\.\w+:\s*/, '');
          } else if (/priority/i.test(trimmed)) {
            newFieldErrors.priority = trimmed.replace(/^body\.\w+:\s*/, '');
          }
        }
        if (Object.keys(newFieldErrors).length > 0) {
          setFieldErrors(newFieldErrors);
        } else {
          setFormError(msg || 'Validation failed. Please review the inputs.');
        }
      } else {
        setFormError('Unable to create ticket. Please check your connection and try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const combinedLen = title.trim().length + description.trim().length;
  const hasConfidentSuggestion = Boolean(triageResult?.suggested_category);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="border-b border-line pb-4">
        <h1 className="font-serif text-3xl font-semibold text-ink">New ticket</h1>
        <p className="text-muted text-sm mt-1">
          Describe the problem. Suggestions update as you type.
        </p>
      </div>

      {/* Form Level Error Alert */}
      {formError && (
        <div
          role="alert"
          className="p-3.5 bg-coral/10 border border-coral/30 rounded-lg text-xs sm:text-sm text-coral"
        >
          {formError}
        </div>
      )}

      {/* Main Grid: Form on Left, Suggestion Card on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Form */}
        <form onSubmit={handleSubmit} className="lg:col-span-7 space-y-5 bg-paper2/50 border border-line rounded-lg p-5 sm:p-6">
          {/* Title Field */}
          <div>
            <label
              htmlFor={titleInputId}
              className="block text-xs sm:text-sm font-semibold text-ink mb-1.5"
            >
              Title <span className="text-coral">*</span>
            </label>
            <input
              id={titleInputId}
              type="text"
              value={title}
              maxLength={255}
              onChange={(e) => {
                setTitle(e.target.value);
                if (fieldErrors.title) {
                  setFieldErrors((prev) => {
                    const copy = { ...prev };
                    delete copy.title;
                    return copy;
                  });
                }
              }}
              placeholder="e.g. Cannot access staging VPN after password reset"
              className={`w-full bg-paper border rounded px-3 py-2 text-xs sm:text-sm text-ink placeholder-muted/60 focus:outline-none focus:ring-2 focus:ring-teal ${
                fieldErrors.title ? 'border-coral' : 'border-line'
              }`}
            />
            {fieldErrors.title && (
              <p className="text-coral text-xs mt-1.5">{fieldErrors.title}</p>
            )}
          </div>

          {/* Description Field */}
          <div>
            <label
              htmlFor={descInputId}
              className="block text-xs sm:text-sm font-semibold text-ink mb-1.5"
            >
              Description <span className="text-coral">*</span>
            </label>
            <textarea
              id={descInputId}
              rows={6}
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                if (fieldErrors.description) {
                  setFieldErrors((prev) => {
                    const copy = { ...prev };
                    delete copy.description;
                    return copy;
                  });
                }
              }}
              placeholder="Provide exact details of the incident or request, error messages, and troubleshooting steps taken..."
              className={`w-full bg-paper border rounded px-3 py-2 text-xs sm:text-sm text-ink placeholder-muted/60 focus:outline-none focus:ring-2 focus:ring-teal ${
                fieldErrors.description ? 'border-coral' : 'border-line'
              }`}
            />
            {fieldErrors.description && (
              <p className="text-coral text-xs mt-1.5">{fieldErrors.description}</p>
            )}
          </div>

          {/* Duplicate Ticket Warning Card (directly under Description) */}
          {activeDuplicates.length > 0 && (
            <div
              role="status"
              aria-live="polite"
              className="rounded-lg border border-amber/30 bg-amber/10 p-4 sm:p-5 space-y-4"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber text-paper text-xs font-bold shrink-0"
                  >
                    !
                  </span>
                  <h3 className="font-serif font-semibold text-ink text-sm sm:text-base">
                    {isRequester
                      ? 'You already have a similar ticket'
                      : 'Possible duplicate'}
                  </h3>
                </div>
                <p className="text-xs sm:text-sm text-ink/80 mt-1">
                  {isRequester
                    ? activeDuplicates.length === 1
                      ? '1 open ticket uses very similar wording'
                      : `${activeDuplicates.length} open tickets use very similar wording`
                    : activeDuplicates.length === 1
                    ? '1 open ticket uses very similar wording. Take a quick look before you submit.'
                    : `${activeDuplicates.length} open tickets use very similar wording. Take a quick look before you submit.`}
                </p>
              </div>

              <div className="space-y-3">
                {activeDuplicates.map((dup) => (
                  <div
                    key={dup.id}
                    className="p-3 bg-paper border border-line rounded-md flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="space-y-1.5 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-semibold text-ink/70">
                          #{dup.id}
                        </span>
                        <span className="font-medium text-xs sm:text-sm text-ink truncate">
                          {dup.title}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                        <StatusBadge status={dup.status} />
                        <PriorityBadge priority={dup.priority} />
                        <span>·</span>
                        <span>
                          Very similar wording · opened {formatRelativeTime(dup.created_at)}
                        </span>
                      </div>
                    </div>
                    <div className="shrink-0 flex items-center">
                      <a
                        href={`/tickets/${dup.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Open ticket #${dup.id}`}
                        className="text-xs font-medium text-teal hover:underline px-2.5 py-1.5 rounded bg-tealLight/20 hover:bg-tealLight/40 transition-colors inline-flex items-center gap-1 focus:outline-none focus:ring-2 focus:ring-teal"
                      >
                        Open ticket
                        <span aria-hidden="true">↗</span>
                      </a>
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-2 border-t border-amber/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setDismissedDuplicateIds((prev) => [
                      ...prev,
                      ...activeDuplicates.map((d) => d.id),
                    ]);
                  }}
                  className="px-3 py-1.5 rounded bg-paper border border-line text-xs font-medium text-ink hover:bg-paper2 transition-colors focus:outline-none focus:ring-2 focus:ring-teal self-start sm:self-auto"
                >
                  Not a duplicate, continue
                </button>
                <span className="text-[11px] sm:text-xs text-muted">
                  You can still submit. This is a text match, not a guarantee.
                </span>
              </div>
            </div>
          )}

          {/* Dismissed Duplicate Notice */}
          {isDuplicateDismissed && (
            <div
              role="status"
              aria-live="polite"
              className="rounded-lg border border-dashed border-line bg-paper2/50 px-4 py-2.5 text-xs text-muted flex items-center justify-between gap-2"
            >
              <span>Marked as not a duplicate. Warning hidden for this draft.</span>
              <button
                type="button"
                onClick={() => {
                  setDismissedDuplicateIds([]);
                }}
                className="text-teal font-medium hover:underline focus:outline-none focus:ring-2 focus:ring-teal rounded"
              >
                Undo
              </button>
            </div>
          )}

          {/* Two-column row: Category & Priority */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Category Select */}
            <div>
              <label
                htmlFor={catInputId}
                className="block text-xs sm:text-sm font-semibold text-ink mb-1.5"
              >
                Category <span className="text-coral">*</span>
              </label>
              <select
                id={catInputId}
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value as TicketCategory);
                  if (fieldErrors.category) {
                    setFieldErrors((prev) => {
                      const copy = { ...prev };
                      delete copy.category;
                      return copy;
                    });
                  }
                }}
                className={`w-full bg-paper border rounded px-3 py-2 text-xs sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-teal ${
                  fieldErrors.category ? 'border-coral' : 'border-line'
                }`}
              >
                <option value="">Choose a category...</option>
                {CATEGORY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {fieldErrors.category && (
                <p className="text-coral text-xs mt-1.5">{fieldErrors.category}</p>
              )}
            </div>

            {/* Priority Select */}
            <div>
              <label
                htmlFor={prioInputId}
                className="block text-xs sm:text-sm font-semibold text-ink mb-1.5"
              >
                Priority
              </label>
              <select
                id={prioInputId}
                value={priority}
                onChange={(e) => setPriority(e.target.value as TicketPriority)}
                className="w-full bg-paper border border-line rounded px-3 py-2 text-xs sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-teal"
              >
                {PRIORITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {fieldErrors.priority && (
                <p className="text-coral text-xs mt-1.5">{fieldErrors.priority}</p>
              )}
            </div>
          </div>

          {/* Form Actions */}
          <div className="pt-4 border-t border-line flex items-center justify-between gap-3">
            <Link
              to="/tickets"
              className="px-4 py-2 text-xs sm:text-sm font-medium text-muted hover:text-ink transition-colors focus:outline-none focus:underline"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={submitting}
              className="px-5 py-2.5 rounded bg-teal text-paper text-xs sm:text-sm font-medium hover:bg-teal/90 disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-teal focus:ring-offset-2"
            >
              {submitting ? 'Creating ticket...' : 'Create ticket'}
            </button>
          </div>
        </form>

        {/* Right Column: AI Triage Advisory Card */}
        <div
          className="lg:col-span-5 bg-paper border border-line rounded-lg p-5 sm:p-6 space-y-4 shadow-xs"
          aria-live="polite"
        >
          <div className="flex items-center justify-between border-b border-line pb-2.5">
            <h3 className="font-serif font-semibold text-ink text-sm sm:text-base">
              AI Triage Advisory
            </h3>
            {triageLoading && (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted">
                <span className="w-2.5 h-2.5 border-2 border-teal border-t-transparent rounded-full animate-spin" />
                Analyzing...
              </span>
            )}
          </div>

          {/* Card Body */}
          {triageUnavailable ? (
            <p className="text-xs text-muted italic py-2">Suggestions unavailable</p>
          ) : combinedLen < TRIAGE_BENCHMARKS.minTextLength ? (
            <p className="text-xs text-muted py-2">
              Suggestions appear as you describe the issue (minimum 15 characters).
            </p>
          ) : !hasConfidentSuggestion && !triageLoading ? (
            <p className="text-xs text-muted italic py-2">No confident suggestion yet</p>
          ) : (
            <div className="space-y-4">
              {triageResult?.fallback_reason === 'possible_prompt_injection' && (
                <div className="p-2.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-900 text-xs">
                  Possible prompt injection detected. Showing the similarity-based suggestion instead.
                </div>
              )}
              {/* Category suggestion */}
              {triageResult?.suggested_category && (
                <div className="p-3 bg-paper2/60 border border-line rounded-lg space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-ink">Suggested Category</span>
                    <button
                      type="button"
                      onClick={() => handleApplyCategory(triageResult.suggested_category!)}
                      className="px-2.5 py-1 text-xs rounded bg-teal text-paper font-medium hover:bg-teal/90 transition-colors focus:outline-none focus:ring-2 focus:ring-teal"
                    >
                      Apply category
                    </button>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="px-2.5 py-0.5 rounded text-xs font-medium border bg-tealLight/20 text-teal border-teal/40 capitalize">
                      {triageResult.suggested_category}
                    </span>
                    {typeof triageResult.confidence === 'number' && (
                      <div className="flex-1 flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-paper border border-line rounded-full overflow-hidden">
                          <div
                            className="h-full bg-teal"
                            style={{
                              width: `${Math.round(triageResult.confidence * 100)}%`,
                            }}
                          />
                        </div>
                        <span className="text-[11px] font-mono text-muted">
                          {Math.round(triageResult.confidence * 100)}%
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Priority suggestion with low reliability tag */}
              {triageResult?.suggested_priority && (
                <div className="p-3 bg-paper2/60 border border-line rounded-lg space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-ink">Priority Hint</span>
                      <span className="text-[10px] font-mono font-medium px-1.5 py-0.5 rounded bg-paper2 text-muted border border-line">
                        Low reliability
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleApplyPriority(triageResult.suggested_priority!)}
                      className="px-2.5 py-1 text-xs rounded bg-paper border border-line text-ink font-medium hover:border-teal transition-colors focus:outline-none focus:ring-2 focus:ring-teal"
                    >
                      Apply priority
                    </button>
                  </div>
                  <div>
                    <span className="px-2 py-0.5 rounded text-xs font-mono font-medium border bg-paper text-ink border-line capitalize">
                      {triageResult.suggested_priority}
                    </span>
                  </div>
                </div>
              )}

              {/* Note after applied */}
              {(appliedCategory || appliedPriority) && (
                <p className="text-xs text-teal font-medium">
                  Suggestion applied — you can still change both.
                </p>
              )}

              {/* Evidence: Closest resolved tickets */}
              {triageResult?.evidence && triageResult.evidence.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-line">
                  <h4 className="text-xs font-semibold text-ink">
                    Why: closest resolved tickets
                  </h4>
                  <ul className="space-y-2">
                    {triageResult.evidence.map((item) => (
                      <li
                        key={item.id}
                        className="p-2.5 bg-paper2/40 border border-line rounded flex items-center justify-between gap-2 text-xs"
                      >
                        <div className="truncate flex-1 min-w-0">
                          <Link
                            to={`/tickets/${item.id}`}
                            className="font-mono text-teal hover:underline mr-1.5"
                          >
                            #{item.id}
                          </Link>
                          <span className="text-ink truncate">{item.title}</span>
                        </div>
                        <div className="shrink-0 flex items-center gap-1.5">
                          <span className="text-[11px] font-mono text-muted">
                            {Math.round(item.similarity * 100)}%
                          </span>
                          <div className="w-12 h-1.5 bg-paper border border-line rounded-full overflow-hidden">
                            <div
                              className="h-full bg-teal"
                              style={{
                                width: `${Math.round(item.similarity * 100)}%`,
                              }}
                            />
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Honesty Footer */}
          <div className="pt-3 border-t border-line text-xs text-muted space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-1.5">
              <span>{TRIAGE_HONESTY_SUMMARY}</span>
              <button
                type="button"
                onClick={() => setShowAccuracy(!showAccuracy)}
                aria-expanded={showAccuracy}
                className="text-teal hover:underline text-[11px] font-medium focus:outline-none focus:underline"
              >
                {showAccuracy ? 'Hide note' : 'How accurate is this?'}
              </button>
            </div>
            {showAccuracy && (
              <div className="p-2.5 bg-paper2 rounded border border-line text-[11px] text-ink leading-relaxed">
                {TRIAGE_EXPLANATION}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
