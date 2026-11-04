import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/useAuth';
import { getTicketTriageFeedback, confirmTriageFeedback, updateTicket } from '../../api/tickets';
import type { Ticket, TriageFeedbackRead, TicketCategory, TicketPriority } from '../../api/types';
import { resolveActorName, formatKolkataDetailTime } from './ticketDetailHelpers';

export interface AITriageStripProps {
  ticket: Ticket;
  onTicketUpdated?: (ticket: Ticket) => void;
}

export const AITriageStrip: React.FC<AITriageStripProps> = ({ ticket, onTicketUpdated }) => {
  const { user } = useAuth();
  const isStaff = user?.role === 'agent' || user?.role === 'admin';
  const isAdmin = user?.role === 'admin';
  const isAgent = user?.role === 'agent';

  const [feedback, setFeedback] = useState<TriageFeedbackRead | null>(null);
  const [loadingAction, setLoadingAction] = useState<'apply' | 'confirm' | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;

    if (!isStaff || !ticket.id) {
      return;
    }

    const load = async () => {
      try {
        const data = await getTicketTriageFeedback(ticket.id);
        if (!ignore) {
          setFeedback(data);
        }
      } catch (err: unknown) {
        if (!ignore) {
          // If 404: render nothing silently. If non-404: show nothing silently.
          if (err && typeof err === 'object' && 'status' in err && (err as { status: number }).status !== 404) {
            console.warn('Failed to load triage feedback', err);
          }
          setFeedback(null);
        }
      }
    };

    load();

    return () => {
      ignore = true;
    };
  }, [ticket.id, isStaff]);

  if (!isStaff || !feedback) {
    return null;
  }

  // Method display badge
  const methodLabel = feedback.method.toLowerCase().includes('llm')
    ? 'LLM'
    : feedback.method.toLowerCase().includes('knn')
    ? 'kNN'
    : feedback.method.toUpperCase();

  // Check if current ticket already matches suggested values in BOTH category and priority
  const matchesBoth =
    ticket.category.toLowerCase() === feedback.suggested_category.toLowerCase() &&
    ticket.priority.toLowerCase() === feedback.suggested_priority.toLowerCase();

  // Priority difference helper text for agents
  const prioDiffers =
    ticket.priority.toLowerCase() !== feedback.suggested_priority.toLowerCase();
  const showAdminPrioNotice = isAgent && prioDiffers;

  // Review status
  const isReviewed = Boolean(feedback.final_set_at || feedback.final_category);
  const reviewerName = feedback.final_set_by
    ? resolveActorName(feedback.final_set_by, ticket, user?.id)
    : 'an agent';
  const reviewedTime = feedback.final_set_at ? formatKolkataDetailTime(feedback.final_set_at) : '';

  // 1. Apply AI suggestion handler
  const handleApply = async () => {
    if (loadingAction !== null) return;
    setLoadingAction('apply');
    setActionError(null);
    setActionMessage(null);

    try {
      let updatedTicket = ticket;
      if (isAdmin) {
        // Admin applies BOTH category and priority
        updatedTicket = await updateTicket(ticket.id, {
          category: feedback.suggested_category as TicketCategory,
          priority: feedback.suggested_priority as TicketPriority,
        });
      } else {
        // Agent applies ONLY category
        updatedTicket = await updateTicket(ticket.id, {
          category: feedback.suggested_category as TicketCategory,
        });
      }

      // Explicitly confirm feedback
      const updatedFb = await confirmTriageFeedback(ticket.id);
      setFeedback(updatedFb);
      setActionMessage('AI suggestion applied successfully');
      if (onTicketUpdated) {
        onTicketUpdated(updatedTicket);
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'message' in err) {
        setActionError((err as { message: string }).message);
      } else {
        setActionError('Failed to apply AI suggestion');
      }
    } finally {
      setLoadingAction(null);
    }
  };

  // 2. Mark reviewed as is handler
  const handleMarkReviewed = async () => {
    if (loadingAction !== null) return;
    setLoadingAction('confirm');
    setActionError(null);
    setActionMessage(null);

    try {
      const updatedFb = await confirmTriageFeedback(ticket.id);
      setFeedback(updatedFb);
      setActionMessage('Marked as reviewed');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'message' in err) {
        setActionError((err as { message: string }).message);
      } else {
        setActionError('Failed to mark reviewed');
      }
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div
      role="region"
      aria-label="AI Triage Review"
      className="bg-paper border border-line rounded-lg p-5 flex flex-col gap-4 shadow-xs"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line pb-3">
        <div className="flex items-center gap-2">
          <span className="font-serif text-base font-semibold text-ink">AI Triage</span>
        </div>
        <span
          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium border bg-paper2 text-ink border-line"
          aria-label={`Triage method: ${methodLabel}`}
        >
          {methodLabel}
        </span>
      </div>

      {/* 3 Columns Comparison */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
        {/* Column 1: AI Suggested */}
        <div className="bg-paper2/50 border border-line/70 rounded p-3 flex flex-col gap-1.5">
          <div className="font-mono uppercase font-semibold text-muted text-[11px]">
            AI suggested
          </div>
          <div>
            <span className="text-muted">Category: </span>
            <span className="font-medium text-ink capitalize">{feedback.suggested_category}</span>
          </div>
          <div>
            <span className="text-muted">Priority: </span>
            <span className="font-medium text-ink capitalize">{feedback.suggested_priority}</span>
          </div>
        </div>

        {/* Column 2: Requester Chose */}
        <div className="bg-paper2/50 border border-line/70 rounded p-3 flex flex-col gap-1.5">
          <div className="font-mono uppercase font-semibold text-muted text-[11px]">
            Requester chose
          </div>
          <div>
            <span className="text-muted">Category: </span>
            <span className="font-medium text-ink capitalize">{feedback.requester_category}</span>
          </div>
          <div>
            <span className="text-muted">Priority: </span>
            <span className="font-medium text-ink capitalize">{feedback.requester_priority}</span>
          </div>
        </div>

        {/* Column 3: Current Ticket */}
        <div className="bg-paper2/50 border border-line/70 rounded p-3 flex flex-col gap-1.5">
          <div className="font-mono uppercase font-semibold text-muted text-[11px]">
            Current ticket
          </div>
          <div>
            <span className="text-muted">Category: </span>
            <span className="font-medium text-ink capitalize">{ticket.category}</span>
          </div>
          <div>
            <span className="text-muted">Priority: </span>
            <span className="font-medium text-ink capitalize">{ticket.priority}</span>
          </div>
        </div>
      </div>

      {/* Footer: Status, Buttons & Notices */}
      <div className="border-t border-line pt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        {/* Status Line */}
        <div className="text-muted">
          <span className="font-semibold text-ink">Status: </span>
          {isReviewed ? (
            <span>
              Reviewed by {reviewerName} on {reviewedTime}
            </span>
          ) : (
            <span className="text-amber font-medium">Awaiting your review</span>
          )}
        </div>

        {/* Buttons & Helper Text */}
        <div className="flex flex-wrap items-center gap-2">
          {showAdminPrioNotice && (
            <span className="text-muted text-[11px] italic mr-1">
              Priority changes need an admin
            </span>
          )}

          {!matchesBoth && (
            <button
              type="button"
              onClick={handleApply}
              disabled={loadingAction !== null}
              className="px-3 py-1.5 text-xs font-medium text-white bg-teal hover:bg-tealHover rounded transition-colors shadow-xs disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-teal/30"
            >
              {loadingAction === 'apply' ? 'Applying...' : 'Apply AI suggestion'}
            </button>
          )}

          <button
            type="button"
            onClick={handleMarkReviewed}
            disabled={loadingAction !== null}
            className="px-3 py-1.5 text-xs font-medium text-ink bg-paper2 hover:bg-paper3 border border-line rounded transition-colors shadow-xs disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-teal"
          >
            {loadingAction === 'confirm' ? 'Saving...' : 'Mark reviewed as is'}
          </button>
        </div>
      </div>

      {/* Messages */}
      {actionMessage && (
        <div
          role="status"
          className="p-2.5 bg-teal/10 border border-teal/30 rounded text-xs text-teal font-medium"
        >
          {actionMessage}
        </div>
      )}
      {actionError && (
        <div
          role="alert"
          className="p-2.5 bg-coral/10 border border-coral/30 rounded text-xs text-coral font-medium"
        >
          {actionError}
        </div>
      )}
    </div>
  );
};
