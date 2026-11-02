import React from 'react';
import { useParams } from 'react-router-dom';

interface PlaceholderProps {
  title: string;
  description: string;
}

export const PlaceholderPage: React.FC<PlaceholderProps> = ({ title, description }) => {
  return (
    <div className="bg-paper2 border border-line rounded-lg p-8 max-w-2xl">
      <h1 className="font-serif text-3xl font-semibold text-ink mb-2">{title}</h1>
      <p className="text-muted text-sm mb-6">{description}</p>
      <div className="inline-flex items-center px-3 py-1 rounded bg-paper border border-line text-xs font-mono text-muted">
        Coming in the next phase
      </div>
    </div>
  );
};

export const TicketsPage: React.FC = () => (
  <PlaceholderPage
    title="Tickets"
    description="View, filter, and inspect helpdesk tickets with business-hours SLA status."
  />
);

export const TicketDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  return (
    <PlaceholderPage
      title={`Ticket #${id || ''}`}
      description="Detailed ticket timeline, conversation history, and SLA business-hours breakdown."
    />
  );
};

export const NewTicketPage: React.FC = () => (
  <PlaceholderPage
    title="New Ticket"
    description="Submit a new incident or service request with AI-assisted category triage."
  />
);

export const ReportsPage: React.FC = () => (
  <PlaceholderPage
    title="Operational Reports"
    description="Staff operational analytics, agent rankings, and business-hours SLA breach metrics."
  />
);

export const HolidaysPage: React.FC = () => (
  <PlaceholderPage
    title="Organizational Holidays"
    description="Admin configuration for holiday calendars pausing the operational SLA clock."
  />
);
