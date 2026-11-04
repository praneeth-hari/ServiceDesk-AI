import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/useAuth';
import { getFriendlyErrorMessage } from '../../utils/errors';
import {
  getTicket,
  listComments,
  addComment,
  getHistory,
  changeStatus,
  assignTicket,
  getSimilarTickets,
  listAgents,
} from '../../api/tickets';
import type {
  Ticket,
  Comment,
  StatusHistory,
  SimilarTicket,
  TicketStatus,
  User,
} from '../../api/types';
import { StatusBadge, PriorityBadge } from './components/Badges';
import { AITriageStrip } from './AITriageStrip';
import { AIAssistCard } from './AIAssistCard';
import { classifyTicketSla } from './slaState';
import {
  computeBusinessMinutesRemaining,
  formatDurationShort,
} from './businessTime';
import {
  resolveActorName,
  mergeTimeline,
  formatKolkataDetailTime,
  formatKolkataDueTime,
  getAllowedActions,
  formatStatusLabel,
} from './ticketDetailHelpers';

export const TicketDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const ticketId = parseInt(id || '', 10);
  const location = useLocation();
  const { user } = useAuth();
  const isStaff = user?.role === 'agent' || user?.role === 'admin';
  const isAdmin = user?.role === 'admin';

  // Navigation back URL
  const backUrl = (location.state as { from?: string } | null)?.from || '/tickets';

  // Data state
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [history, setHistory] = useState<StatusHistory[]>([]);
  const [similarTickets, setSimilarTickets] = useState<SimilarTicket[]>([]);
  const [agents, setAgents] = useState<User[]>([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Composer state
  const [replyText, setReplyText] = useState('');
  const [isInternal, setIsInternal] = useState(false);
  const [submittingComment, setSubmittingComment] = useState(false);
  const [commentError, setCommentError] = useState<string | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // Actions state
  const [actionLoading, setActionLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [confirmingClose, setConfirmingClose] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [assignError, setAssignError] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState(0);

  // Data fetching
  useEffect(() => {
    let ignore = false;

    if (isNaN(ticketId)) {
      return;
    }

    const load = async () => {
      try {
        const [ticketData, commentsData, historyData] = await Promise.all([
          getTicket(ticketId),
          listComments(ticketId),
          getHistory(ticketId),
        ]);

        if (ignore) return;

        setTicket(ticketData);
        setComments(commentsData);
        setHistory(historyData);
        setErrorStatus(null);
        setErrorMessage(null);
        setLoading(false);

        // Staff only queries
        if (isStaff) {
          getSimilarTickets(ticketId, 5)
            .then((sim) => {
              if (!ignore) setSimilarTickets(sim);
            })
            .catch(() => {
              if (!ignore) setSimilarTickets([]);
            });

          if (isAdmin) {
            listAgents()
              .then((agentList) => {
                if (!ignore) setAgents(agentList);
              })
              .catch(() => {
                if (!ignore) setAgents([]);
              });
          }
        }
      } catch (err: unknown) {
        if (ignore) return;
        setLoading(false);
        if (err && typeof err === 'object' && 'status' in err) {
          const status = (err as { status: number }).status;
          setErrorStatus(status);
          if (status === 404) {
            setErrorMessage('Ticket not found');
          } else {
            setErrorMessage(getFriendlyErrorMessage(err, 'Failed to load ticket'));
          }
        } else {
          setErrorMessage('Cannot reach the server. Please try again.');
        }
      }
    };

    load();

    return () => {
      ignore = true;
    };
  }, [ticketId, isStaff, isAdmin, reloadKey]);

  const handleRetry = () => {
    setLoading(true);
    setReloadKey((prev) => prev + 1);
  };

  // Reply handler
  const handleInsertReply = (draftText: string) => {
    setReplyText((prev) => {
      const combined = prev.trim() ? `${prev}\n\n${draftText}` : draftText;
      return combined.slice(0, 2000);
    });
    composerRef.current?.focus();
    if (typeof composerRef.current?.scrollIntoView === 'function') {
      composerRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  const handlePostComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!replyText.trim() || submittingComment || !ticket) return;

    setSubmittingComment(true);
    setCommentError(null);

    try {
      const newComment = await addComment(ticket.id, {
        body: replyText.trim(),
        is_internal: isStaff && isInternal,
      });

      setComments((prev) => [...prev, newComment]);
      setReplyText('');
      setIsInternal(false);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'message' in err) {
        setCommentError((err as { message: string }).message);
      } else {
        setCommentError('Failed to post comment. Please try again.');
      }
    } finally {
      setSubmittingComment(false);
    }
  };

  // Status transition handler
  const handleStatusTransition = async (targetStatus: TicketStatus) => {
    if (!ticket || actionLoading) return;

    setActionLoading(true);
    setStatusError(null);

    try {
      const updatedTicket = await changeStatus(ticket.id, targetStatus);
      setTicket(updatedTicket);
      setConfirmingClose(false);

      // Refetch history and comments to sync timeline
      const [updatedHistory, updatedComments] = await Promise.all([
        getHistory(ticket.id),
        listComments(ticket.id),
      ]);
      setHistory(updatedHistory);
      setComments(updatedComments);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'message' in err) {
        setStatusError((err as { message: string }).message);
      } else {
        setStatusError('Status transition failed.');
      }
    } finally {
      setActionLoading(false);
    }
  };

  // Assignment handlers
  const handleAssignToMe = async () => {
    if (!ticket || !user || actionLoading) return;
    setActionLoading(true);
    setAssignError(null);

    try {
      const updated = await assignTicket(ticket.id, user.id);
      setTicket(updated);
      const updatedHistory = await getHistory(ticket.id);
      setHistory(updatedHistory);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'message' in err) {
        setAssignError((err as { message: string }).message);
      } else {
        setAssignError('Failed to assign ticket.');
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleAdminAssign = async () => {
    const assigneeId = parseInt(selectedAgentId, 10);
    if (!ticket || isNaN(assigneeId) || actionLoading) return;
    setActionLoading(true);
    setAssignError(null);

    try {
      const updated = await assignTicket(ticket.id, assigneeId);
      setTicket(updated);
      setSelectedAgentId('');
      const updatedHistory = await getHistory(ticket.id);
      setHistory(updatedHistory);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'message' in err) {
        setAssignError((err as { message: string }).message);
      } else {
        setAssignError('Failed to assign ticket.');
      }
    } finally {
      setActionLoading(false);
    }
  };

  // 1. Loading state
  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8 animate-pulse flex flex-col gap-6">
        <div className="h-4 w-24 bg-paper3 rounded" />
        <div className="h-8 w-2/3 bg-paper3 rounded" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 flex flex-col gap-6">
            <div className="h-36 bg-paper rounded-lg border border-line" />
            <div className="h-64 bg-paper rounded-lg border border-line" />
          </div>
          <div className="flex flex-col gap-6">
            <div className="h-32 bg-paper rounded-lg border border-line" />
            <div className="h-40 bg-paper rounded-lg border border-line" />
          </div>
        </div>
      </div>
    );
  }

  // 2. 404 Not Found state
  if (isNaN(ticketId) || errorStatus === 404) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-paper2 border border-line flex items-center justify-center text-muted font-mono">
          404
        </div>
        <h1 className="font-serif text-2xl font-bold text-ink mb-2">Ticket not found</h1>
        <p className="text-muted text-sm mb-6">
          The ticket you are looking for does not exist or you do not have permission to view it.
        </p>
        <Link
          to="/tickets"
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-teal hover:bg-tealHover rounded-md transition-colors shadow-xs"
        >
          &larr; Back to tickets
        </Link>
      </div>
    );
  }

  // 3. General Error state
  if (errorMessage && !ticket) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="p-4 bg-coral/10 border border-coral/30 rounded-lg text-coral text-sm mb-6 inline-block">
          {errorMessage}
        </div>
        <div>
          <button
            type="button"
            onClick={handleRetry}
            className="px-4 py-2 text-sm font-medium text-white bg-teal hover:bg-tealHover rounded-md transition-colors shadow-xs"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-paper2 border border-line flex items-center justify-center text-muted font-mono">
          404
        </div>
        <h1 className="font-serif text-2xl font-bold text-ink mb-2">Ticket not found</h1>
        <p className="text-muted text-sm mb-6">
          The ticket you are looking for does not exist or you do not have permission to view it.
        </p>
        <Link
          to="/tickets"
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-teal hover:bg-tealHover rounded-md transition-colors shadow-xs"
        >
          &larr; Back to tickets
        </Link>
      </div>
    );
  }

  // Compute SLA and Timeline
  const slaInfo = classifyTicketSla(ticket);
  const remainingMins = computeBusinessMinutesRemaining(ticket.due_at);
  const isResolvedOrClosed = ticket.status === 'resolved' || ticket.status === 'closed';
  const visibleComments = isStaff ? comments : comments.filter((c) => !c.is_internal);
  const timelineItems = mergeTimeline(visibleComments, history);
  const allowedActions = getAllowedActions(ticket.status);

  // Big SLA Text computation
  const getSlaBigText = () => {
    if (isResolvedOrClosed) {
      return slaInfo.category === 'resolvedLate' ? 'Resolved late' : 'Met';
    }
    if (slaInfo.category === 'paused') {
      return 'Paused';
    }
    if (slaInfo.category === 'breached') {
      return `breached ${formatDurationShort(Math.abs(remainingMins))}`;
    }
    return `${formatDurationShort(remainingMins)} left`;
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 sm:py-8 flex flex-col gap-6">
      {/* Back Link and Header */}
      <div>
        <Link
          to={backUrl}
          className="inline-flex items-center gap-1 text-sm font-medium text-teal hover:underline mb-2 transition-colors focus:outline-none focus:ring-1 focus:ring-teal"
        >
          &larr; Tickets
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h1 className="font-serif text-2xl sm:text-3xl font-semibold text-ink tracking-tight flex items-center gap-2">
            <span className="font-mono text-muted text-xl sm:text-2xl font-normal">#{ticket.id}</span>
            <span>{ticket.title}</span>
          </h1>
          <div className="flex items-center gap-2 shrink-0">
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium border bg-paper2 text-ink border-line capitalize">
              {ticket.category}
            </span>
          </div>
        </div>
      </div>

      {/* AI Triage Strip (Staff only) */}
      <AITriageStrip
        ticket={ticket}
        onTicketUpdated={(updated) => setTicket(updated)}
      />

      {/* Requester Paused SLA Banner */}
      {!isStaff && ticket.status === 'waiting_on_requester' && (
        <div
          role="status"
          className="p-4 bg-purple/10 border border-purple/30 rounded-lg flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
        >
          <div>
            <p className="font-semibold text-sm text-ink">Waiting for your reply.</p>
            <p className="text-xs text-muted">The SLA clock is paused until you answer.</p>
          </div>
          <button
            type="button"
            onClick={() => composerRef.current?.focus()}
            className="px-3 py-1.5 text-xs font-medium text-white bg-purple hover:bg-purple/90 rounded transition-colors shadow-xs shrink-0 focus:outline-none focus:ring-2 focus:ring-purple/40"
          >
            Reply now
          </button>
        </div>
      )}

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        {/* Left Column: Description, Timeline, Reply Composer */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Description Card */}
          <div className="bg-paper border border-line rounded-lg p-5 shadow-xs">
            <h2 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold mb-2">
              Description
            </h2>
            <div className="text-ink text-sm sm:text-base whitespace-pre-wrap leading-relaxed">
              {ticket.description}
            </div>
          </div>

          {/* AI Assist Card (Staff only) */}
          {isStaff && (
            <AIAssistCard
              ticketId={ticket.id}
              onInsertReply={handleInsertReply}
            />
          )}

          {/* Activity Timeline */}
          <div className="flex flex-col gap-4">
            <h2 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">
              Activity
            </h2>

            <div aria-live="polite" className="flex flex-col gap-3">
              {timelineItems.length === 0 ? (
                <div className="p-4 bg-paper border border-line rounded-lg text-xs text-muted text-center font-mono">
                  No activity recorded yet.
                </div>
              ) : (
                timelineItems.map((item) => {
                  if (item.kind === 'history') {
                    const h = item.history;
                    const actorName = resolveActorName(h.changed_by_id, ticket, user?.id, h.actor_name);
                    const isCreation = h.from_status === null;

                    return (
                      <div
                        key={`h-${h.id}`}
                        className="flex items-start gap-3 px-3 py-2 text-xs text-muted font-sans"
                      >
                        <span className="w-2.5 h-2.5 rounded-full bg-purple shrink-0 mt-1" />
                        <div className="flex flex-wrap items-center gap-1.5">
                          {isCreation ? (
                            <span className="font-medium text-ink">Ticket created</span>
                          ) : (
                            <span className="font-medium text-ink">
                              {formatStatusLabel(h.from_status)} &rarr; {formatStatusLabel(h.to_status)}
                            </span>
                          )}
                          <span>by</span>
                          <span className="font-medium text-ink">{actorName}</span>
                          <span className="text-[10px] text-muted">·</span>
                          <time className="font-mono text-[11px] text-muted">
                            {formatKolkataDetailTime(h.created_at)}
                          </time>
                        </div>
                      </div>
                    );
                  }

                  const c = item.comment;
                  const authorName = resolveActorName(c.author_id, ticket, user?.id, c.author_name);

                  if (c.is_internal) {
                    return (
                      <div
                        key={`c-${c.id}`}
                        className="bg-amber/10 border border-amber/30 rounded-lg p-4 flex flex-col gap-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm text-ink">{authorName}</span>
                            <span className="text-[10px] font-mono uppercase font-bold text-amber border border-amber/40 bg-amber/15 px-1.5 py-0.5 rounded">
                              internal note
                            </span>
                          </div>
                          <time className="font-mono text-xs text-muted">
                            {formatKolkataDetailTime(c.created_at)}
                          </time>
                        </div>
                        <div className="text-ink text-sm whitespace-pre-wrap leading-relaxed">
                          {c.body}
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div
                      key={`c-${c.id}`}
                      className="bg-paper border border-line rounded-lg p-4 flex flex-col gap-2 shadow-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-sm text-ink">{authorName}</span>
                        <time className="font-mono text-xs text-muted">
                          {formatKolkataDetailTime(c.created_at)}
                        </time>
                      </div>
                      <div className="text-ink text-sm whitespace-pre-wrap leading-relaxed">
                        {c.body}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Reply Composer */}
          <div className="mt-2">
            {ticket.status === 'closed' ? (
              <div className="p-4 bg-paper2 border border-line rounded-lg text-sm text-ink">
                <p>This ticket is closed. Open a new ticket if the problem comes back.</p>
                <Link
                  to="/tickets/new"
                  className="text-teal font-medium hover:underline inline-block mt-2 focus:outline-none focus:ring-1 focus:ring-teal"
                >
                  New ticket &rarr;
                </Link>
              </div>
            ) : (
              <form
                onSubmit={handlePostComment}
                className="bg-paper border border-line rounded-lg p-4 flex flex-col gap-3 shadow-xs"
              >
                <label
                  htmlFor="reply-composer-textarea"
                  className="text-xs font-mono uppercase tracking-wider text-muted font-semibold"
                >
                  Add reply
                </label>
                <textarea
                  id="reply-composer-textarea"
                  ref={composerRef}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  maxLength={2000}
                  rows={3}
                  placeholder="Type your message..."
                  className="w-full p-2.5 text-sm bg-white border border-line rounded-md text-ink placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-teal/30 focus:border-teal transition-all resize-y"
                />

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-muted font-mono">
                  <span>{replyText.length} / 2000</span>
                  {isStaff && (
                    <label className="flex items-center gap-2 cursor-pointer font-sans select-none text-ink">
                      <input
                        type="checkbox"
                        checked={isInternal}
                        onChange={(e) => setIsInternal(e.target.checked)}
                        className="rounded border-line text-amber focus:ring-amber/30"
                      />
                      <span>Internal note (hidden from the requester)</span>
                    </label>
                  )}
                </div>

                {commentError && (
                  <div role="alert" className="text-xs text-coral bg-coral/10 border border-coral/30 p-2 rounded">
                    {commentError}
                  </div>
                )}

                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={!replyText.trim() || submittingComment}
                    className="px-4 py-1.5 text-sm font-medium text-white bg-teal hover:bg-tealHover rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-xs focus:outline-none focus:ring-2 focus:ring-teal/40"
                  >
                    {submittingComment ? 'Posting...' : 'Post'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>

        {/* Right Column: SLA, Details, Actions, Similar */}
        <div className="flex flex-col gap-6">
          {/* 1. SLA Card */}
          <div className="bg-paper border border-line rounded-lg p-5 flex flex-col gap-3 shadow-xs">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">
                SLA Status
              </h2>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${slaInfo.bgClass} ${slaInfo.textClass} ${slaInfo.borderClass}`}
              >
                {slaInfo.label}
              </span>
            </div>

            <div className="text-2xl font-serif font-bold text-ink">
              {getSlaBigText()}
            </div>

            {/* Due Date or Paused Time */}
            <div className="text-xs text-muted font-sans">
              {slaInfo.category === 'paused' ? (
                <span>
                  paused since {formatKolkataDetailTime(ticket.sla_paused_at || ticket.updated_at)}
                </span>
              ) : !isResolvedOrClosed && ticket.due_at ? (
                <span>{formatKolkataDueTime(ticket.due_at)}</span>
              ) : null}
            </div>

            {/* SLA Elapsed Progress Bar */}
            {!isResolvedOrClosed && (
              <div className="w-full bg-paper3 rounded-full h-1.5 overflow-hidden mt-1">
                <div
                  className={`h-full transition-all ${
                    slaInfo.category === 'atRisk'
                      ? 'bg-amber'
                      : slaInfo.category === 'breached'
                      ? 'bg-coral'
                      : slaInfo.category === 'paused'
                      ? 'bg-purple'
                      : 'bg-teal'
                  }`}
                  style={{ width: `${Math.round(slaInfo.ratio * 100)}%` }}
                />
              </div>
            )}
          </div>

          {/* 2. Details Card */}
          <div className="bg-paper border border-line rounded-lg p-5 flex flex-col gap-3 shadow-xs">
            <h2 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">
              Details
            </h2>
            <dl className="grid grid-cols-3 gap-2 text-xs">
              <dt className="text-muted">Requester</dt>
              <dd className="col-span-2 text-ink font-medium truncate">
                {ticket.requester_name || `User #${ticket.requester_id}`}
              </dd>

              <dt className="text-muted">Assignee</dt>
              <dd className="col-span-2 text-ink font-medium truncate">
                {ticket.assignee_name || <span className="text-muted italic">Unassigned</span>}
              </dd>

              <dt className="text-muted">Category</dt>
              <dd className="col-span-2 capitalize text-ink font-mono font-medium">
                {ticket.category}
              </dd>

              <dt className="text-muted">Created</dt>
              <dd className="col-span-2 font-mono text-muted">
                {formatKolkataDetailTime(ticket.created_at)}
              </dd>
            </dl>
          </div>

          {/* 3. Actions Card (Staff Only) */}
          {isStaff && (
            <div className="bg-paper border border-line rounded-lg p-5 flex flex-col gap-3 shadow-xs">
              <h2 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">
                Actions
              </h2>

              {ticket.status === 'closed' ? (
                <p className="text-xs text-muted font-sans">
                  No actions available for closed tickets.
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  {/* Status transitions */}
                  {allowedActions.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {allowedActions.map((action) => {
                        if (action.confirmRequired) {
                          if (confirmingClose) {
                            return (
                              <div key={action.targetStatus} className="flex items-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => handleStatusTransition(action.targetStatus)}
                                  disabled={actionLoading}
                                  className="px-3 py-1.5 text-xs font-medium text-white bg-coral hover:bg-coral/90 rounded transition-colors shadow-xs"
                                >
                                  Confirm close?
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setConfirmingClose(false)}
                                  disabled={actionLoading}
                                  className="px-2 py-1.5 text-xs text-muted hover:text-ink"
                                >
                                  Cancel
                                </button>
                              </div>
                            );
                          }
                          return (
                            <button
                              key={action.targetStatus}
                              type="button"
                              onClick={() => setConfirmingClose(true)}
                              disabled={actionLoading}
                              className="px-3 py-1.5 text-xs font-medium text-ink bg-paper2 hover:bg-paper3 border border-line rounded transition-colors shadow-xs"
                            >
                              {action.label}
                            </button>
                          );
                        }

                        return (
                          <button
                            key={action.targetStatus}
                            type="button"
                            onClick={() => handleStatusTransition(action.targetStatus)}
                            disabled={actionLoading}
                            className="px-3 py-1.5 text-xs font-medium text-white bg-teal hover:bg-tealHover rounded transition-colors shadow-xs"
                          >
                            {action.label}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Transition error display */}
                  {statusError && (
                    <div role="alert" className="text-xs text-coral bg-coral/10 border border-coral/30 p-2 rounded">
                      {statusError}
                    </div>
                  )}

                  {/* Assignment Controls */}
                  <div className="border-t border-line pt-3 flex flex-col gap-2">
                    <span className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">
                      Assignment
                    </span>

                    {/* Agent View: Assign to me */}
                    {user?.role === 'agent' && (
                      <div>
                        {ticket.assignee_id === user.id ? (
                          <span className="text-xs text-muted">Assigned to you</span>
                        ) : (
                          <button
                            type="button"
                            onClick={handleAssignToMe}
                            disabled={actionLoading}
                            className="px-3 py-1.5 text-xs font-medium text-ink bg-paper2 hover:bg-paper3 border border-line rounded transition-colors shadow-xs"
                          >
                            Assign to me
                          </button>
                        )}
                      </div>
                    )}

                    {/* Admin View: Select agent */}
                    {isAdmin && (
                      <div className="flex items-center gap-2">
                        <select
                          aria-label="Select active agent"
                          value={selectedAgentId}
                          onChange={(e) => setSelectedAgentId(e.target.value)}
                          disabled={actionLoading}
                          className="text-xs p-1.5 bg-white border border-line rounded text-ink flex-1 focus:outline-none focus:ring-1 focus:ring-teal"
                        >
                          <option value="">Select agent...</option>
                          {agents.map((agent) => (
                            <option key={agent.id} value={agent.id}>
                              {agent.full_name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={handleAdminAssign}
                          disabled={!selectedAgentId || actionLoading}
                          className="px-3 py-1.5 text-xs font-medium text-white bg-teal hover:bg-tealHover rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-xs"
                        >
                          Assign
                        </button>
                      </div>
                    )}

                    {assignError && (
                      <div role="alert" className="text-xs text-coral bg-coral/10 border border-coral/30 p-2 rounded">
                        {assignError}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 4. Similar Tickets Card (Staff Only) */}
          {isStaff && (
            <div className="bg-paper border border-line rounded-lg p-5 flex flex-col gap-3 shadow-xs">
              <h2 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">
                Similar tickets
              </h2>
              {similarTickets.length > 0 ? (
                <div className="flex flex-col divide-y divide-line">
                  {similarTickets.map((sim) => (
                    <div key={sim.id} className="py-2.5 first:pt-0 last:pb-0 flex flex-col gap-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <Link
                          to={`/tickets/${sim.id}`}
                          className="text-xs font-medium text-ink hover:text-teal line-clamp-1 transition-colors"
                        >
                          #{sim.id} {sim.title}
                        </Link>
                        <StatusBadge status={sim.status} className="shrink-0 text-[10px]" />
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-full bg-paper3 rounded-full h-1 overflow-hidden flex-1">
                          <div
                            className="h-full bg-teal"
                            style={{ width: `${Math.round(sim.similarity * 100)}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-muted shrink-0">
                          {Math.round(sim.similarity * 100)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted">No similar tickets yet</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
