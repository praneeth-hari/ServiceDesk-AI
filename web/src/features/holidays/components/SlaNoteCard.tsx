import React from 'react';

export const SlaNoteCard: React.FC = () => {
  return (
    <div className="bg-paper border border-line rounded-lg p-5 shadow-sm space-y-3">
      <div className="flex items-center gap-2">
        <div className="p-1.5 rounded-full bg-teal/10 text-teal shrink-0">
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <h3 className="font-serif text-sm font-semibold text-ink">
          How it affects SLAs
        </h3>
      </div>

      <div className="text-xs text-muted space-y-2 leading-relaxed">
        <p>
          Official holidays are excluded from business-hour SLA target calculations.
        </p>
        <p>
          When a ticket is scheduled during or across an official holiday, the SLA deadline advances to business hours on the next working day.
        </p>
        <p className="font-medium text-ink bg-paper2/60 p-2.5 rounded border border-line">
          Applies to tickets created or re-timed after this change; existing due dates are not recalculated.
        </p>
      </div>
    </div>
  );
};
