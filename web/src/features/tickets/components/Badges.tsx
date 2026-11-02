import React from 'react';
import type { TicketStatus, TicketPriority } from '../../../api/types';

interface StatusBadgeProps {
  status: TicketStatus;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  const getStyle = () => {
    switch (status) {
      case 'open':
        return 'bg-tealLight/20 text-teal border-teal/40';
      case 'in_progress':
        return 'bg-teal text-paper border-teal';
      case 'waiting_on_requester':
        return 'bg-purple/10 text-purple border-purple/30';
      case 'resolved':
        return 'bg-paper2 text-ink border-line';
      case 'closed':
        return 'bg-paper2 text-muted border-line';
      default:
        return 'bg-paper2 text-muted border-line';
    }
  };

  const getLabel = () => {
    switch (status) {
      case 'open':
        return 'Open';
      case 'in_progress':
        return 'In Progress';
      case 'waiting_on_requester':
        return 'Waiting';
      case 'resolved':
        return 'Resolved';
      case 'closed':
        return 'Closed';
      default:
        return status;
    }
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${getStyle()} ${className}`}
    >
      {getLabel()}
    </span>
  );
};

interface PriorityBadgeProps {
  priority: TicketPriority;
  className?: string;
}

export const PriorityBadge: React.FC<PriorityBadgeProps> = ({ priority, className = '' }) => {
  const getStyle = () => {
    switch (priority) {
      case 'urgent':
        return 'bg-coral/10 text-coral border-coral/30';
      case 'high':
        return 'bg-amber/15 text-amber border-amber/30';
      case 'medium':
        return 'bg-paper2 text-ink border-line';
      case 'low':
        return 'bg-paper2 text-muted border-line';
      default:
        return 'bg-paper2 text-muted border-line';
    }
  };

  const getLabel = () => {
    return priority.charAt(0).toUpperCase() + priority.slice(1);
  };

  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-medium border ${getStyle()} ${className}`}
    >
      {getLabel()}
    </span>
  );
};

