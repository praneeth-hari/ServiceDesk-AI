import React, { useState, useId } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Ticket, TicketStatus } from '../../../api/types';
import {
  buildTimelineWindow,
  mapTimeToPosition,
  formatKolkataDateTime,
  formatKolkataShortDate,
  parseToUtcDate,
  formatDurationShort,
  computeBusinessMinutesRemaining,
} from '../businessTime';
import { classifyTicketSla, sortTicketsDefault, type SlaInfo } from '../slaState';
import {
  DEFAULT_DAY_WIDTH,
  DEFAULT_WEEKEND_WIDTH,
} from '../constants';

interface TimelineViewProps {
  tickets: Ticket[];
  isStaff: boolean;
}

export const TimelineView: React.FC<TimelineViewProps> = ({ tickets, isStaff }) => {
  const navigate = useNavigate();
  const weekendPatternId = useId() + '-weekend';
  const overduePatternId = useId() + '-overdue';

  const [anchorDate, setAnchorDate] = useState<Date>(() => new Date());
  const [hoveredTicket, setHoveredTicket] = useState<{
    ticket: Ticket;
    sla: SlaInfo;
    x: number;
    y: number;
  } | null>(null);

  // 7 business days window
  const windowData = buildTimelineWindow(anchorDate, 7, DEFAULT_DAY_WIDTH, DEFAULT_WEEKEND_WIDTH);
  const now = new Date();
  const nowMs = now.getTime();
  const nowPos = mapTimeToPosition(now, windowData);

  const LABEL_WIDTH = 280;
  const HEADER_HEIGHT = 48;
  const ROW_HEIGHT = 54;
  const totalSvgWidth = LABEL_WIDTH + windowData.totalWidth;
  const sortedTickets = sortTicketsDefault(tickets);
  const totalSvgHeight = HEADER_HEIGHT + Math.max(1, sortedTickets.length) * ROW_HEIGHT + 16;

  // Window shift helpers
  const handlePrev = () => {
    setAnchorDate(new Date(anchorDate.getTime() - 5 * 24 * 60 * 60 * 1000));
  };

  const handleNext = () => {
    setAnchorDate(new Date(anchorDate.getTime() + 5 * 24 * 60 * 60 * 1000));
  };

  const handleToday = () => {
    setAnchorDate(new Date());
  };

  const getStatusPill = (status: TicketStatus) => {
    switch (status) {
      case 'open':
        return { label: 'Open', width: 42, bg: '#99D2CB33', stroke: '#0F766E55', text: '#0F766E' };
      case 'in_progress':
        return { label: 'In Progress', width: 66, bg: '#0F766E', stroke: '#0F766E', text: '#FBF8F3' };
      case 'waiting_on_requester':
        return { label: 'Waiting', width: 48, bg: '#7C5CBF1F', stroke: '#7C5CBF55', text: '#7C5CBF' };
      case 'resolved':
        return { label: 'Resolved', width: 54, bg: '#F2EDE3', stroke: '#E4DED2', text: '#1F2937' };
      case 'closed':
        return { label: 'Closed', width: 46, bg: '#F2EDE3', stroke: '#E4DED2', text: '#6B7280' };
      default:
        return { label: status, width: 50, bg: '#F2EDE3', stroke: '#E4DED2', text: '#6B7280' };
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Timeline Controls */}
      <div className="flex items-center justify-between bg-paper2 border border-line rounded-lg px-4 py-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-serif font-semibold text-ink text-sm">Window:</span>
          <span className="text-muted">
            {formatKolkataDateTime(windowData.startUtcMs).replace(/:\d\d IST$/, '')} –{' '}
            {formatKolkataDateTime(windowData.endUtcMs).replace(/:\d\d IST$/, '')}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handlePrev}
            className="px-2.5 py-1 rounded bg-paper border border-line text-ink hover:border-teal transition-colors"
            aria-label="Previous window"
          >
            ← Previous
          </button>
          <button
            type="button"
            onClick={handleToday}
            className="px-2.5 py-1 rounded bg-paper border border-line text-teal font-medium hover:border-teal transition-colors"
            aria-label="Go to today"
          >
            Today
          </button>
          <button
            type="button"
            onClick={handleNext}
            className="px-2.5 py-1 rounded bg-paper border border-line text-ink hover:border-teal transition-colors"
            aria-label="Next window"
          >
            Next →
          </button>
        </div>
      </div>

      {/* SVG Canvas Container with Horizontal Scroll */}
      <div className="relative border border-line rounded-lg bg-paper overflow-x-auto shadow-xs">
        <svg
          width={totalSvgWidth}
          height={totalSvgHeight}
          className="block select-none"
          role="img"
          aria-label="Ticket SLA Business-Hours Timeline"
        >
          <defs>
            {/* Pattern for weekend hatched band */}
            <pattern
              id={weekendPatternId}
              width="8"
              height="8"
              patternTransform="rotate(45 0 0)"
              patternUnits="userSpaceOnUse"
            >
              <line x1="0" y1="0" x2="0" y2="8" stroke="#E4DED2" strokeWidth="2.5" />
            </pattern>

            {/* Pattern for overdue hatched coral stretch */}
            <pattern
              id={overduePatternId}
              width="8"
              height="8"
              patternTransform="rotate(45 0 0)"
              patternUnits="userSpaceOnUse"
            >
              <line x1="0" y1="0" x2="0" y2="8" stroke="#E4572E" strokeWidth="2.5" />
            </pattern>
          </defs>

          {/* Background */}
          <rect width={totalSvgWidth} height={totalSvgHeight} fill="#FBF8F3" />

          {/* Column Backgrounds and Vertical Separators */}
          {windowData.columns.map((col) => {
            const colX = LABEL_WIDTH + col.x;
            const isWeekend = col.type === 'weekend';

            return (
              <g key={`col-${col.dateStr}-${col.dayOfWeek}`}>
                {isWeekend ? (
                  <rect
                    x={colX}
                    y={0}
                    width={col.width}
                    height={totalSvgHeight}
                    fill={`url(#${weekendPatternId})`}
                    opacity="0.8"
                  />
                ) : (
                  <rect
                    x={colX}
                    y={0}
                    width={col.width}
                    height={totalSvgHeight}
                    fill="#FBF8F3"
                  />
                )}
                {/* Column right hairline border */}
                <line
                  x1={colX + col.width}
                  y1={0}
                  x2={colX + col.width}
                  y2={totalSvgHeight}
                  stroke="#E4DED2"
                  strokeWidth="1"
                />
              </g>
            );
          })}

          {/* Left Header Area */}
          <rect x={0} y={0} width={LABEL_WIDTH} height={HEADER_HEIGHT} fill="#F2EDE3" />
          <line x1={0} y1={HEADER_HEIGHT} x2={totalSvgWidth} y2={HEADER_HEIGHT} stroke="#E4DED2" strokeWidth="1" />
          <line x1={LABEL_WIDTH} y1={0} x2={LABEL_WIDTH} y2={totalSvgHeight} stroke="#E4DED2" strokeWidth="1.5" />

          <text
            x={16}
            y={28}
            fill="#1F2937"
            fontFamily="Source Serif 4, Georgia, serif"
            fontSize="13"
            fontWeight="600"
          >
            Ticket / Assignee
          </text>

          {/* Column Headers */}
          {windowData.columns.map((col) => {
            const colX = LABEL_WIDTH + col.x;
            const isWeekend = col.type === 'weekend';

            return (
              <g key={`hdr-${col.dateStr}-${col.dayOfWeek}`}>
                <rect x={colX} y={0} width={col.width} height={HEADER_HEIGHT} fill="#F2EDE3" opacity="0.6" />
                <line x1={colX} y1={HEADER_HEIGHT} x2={colX + col.width} y2={HEADER_HEIGHT} stroke="#E4DED2" strokeWidth="1" />
                {isWeekend ? (
                  /* Requirement 3: Show only "Sat Sun" (small) in the column header */
                  <text
                    x={colX + col.width / 2}
                    y={28}
                    textAnchor="middle"
                    fill="#6B7280"
                    fontSize="8"
                    fontWeight="600"
                    className="select-none tracking-tighter"
                  >
                    Sat Sun
                  </text>
                ) : (
                  <>
                    <text
                      x={colX + col.width / 2}
                      y={22}
                      textAnchor="middle"
                      fill="#1F2937"
                      fontSize="11"
                      fontWeight="600"
                    >
                      {col.label}
                    </text>
                    <text
                      x={colX + col.width / 2}
                      y={36}
                      textAnchor="middle"
                      fill="#6B7280"
                      fontSize="10"
                    >
                      09:00 – 18:00
                    </text>
                  </>
                )}
              </g>
            );
          })}

          {/* Ticket Rows */}
          {sortedTickets.length === 0 ? (
            <text
              x={LABEL_WIDTH + windowData.totalWidth / 2}
              y={HEADER_HEIGHT + 40}
              textAnchor="middle"
              fill="#6B7280"
              fontSize="13"
            >
              No tickets to display in this range
            </text>
          ) : (
            sortedTickets.map((ticket, index) => {
              const rowY = HEADER_HEIGHT + index * ROW_HEIGHT;
              const isEven = index % 2 === 0;
              const sla = classifyTicketSla(ticket, now);

              const createdTime = parseToUtcDate(ticket.created_at).getTime();
              const dueTime = ticket.due_at ? parseToUtcDate(ticket.due_at).getTime() : null;
              const isResolved = ticket.status === 'resolved' || ticket.status === 'closed';
              const resolvedTime = isResolved ? (ticket.resolved_at ? parseToUtcDate(ticket.resolved_at).getTime() : parseToUtcDate(ticket.updated_at).getTime()) : null;
              const isPaused = ticket.status === 'waiting_on_requester' || ticket.sla_paused_at !== null;
              const pausedTime = ticket.sla_paused_at ? parseToUtcDate(ticket.sla_paused_at).getTime() : null;

              const windowStart = windowData.startUtcMs;
              const windowEnd = windowData.endUtcMs;

              const trackStartX = LABEL_WIDTH;
              const trackEndX = LABEL_WIDTH + windowData.totalWidth;

              const barY = rowY + 23;
              const barHeight = 11;
              const centerY = barY + barHeight / 2;

              const isFocusedOrHovered = hoveredTicket?.ticket.id === ticket.id;
              const pill = getStatusPill(ticket.status);

              // Case 1: Life entirely after window
              const isEntirelyAfterWindow = createdTime > windowEnd;

              // Case 2: Resolved before window
              const isResolvedBeforeWindow = isResolved && resolvedTime !== null && resolvedTime < windowStart;

              // On-track SLA Target Interval: [createdTime, targetDueTime]
              const targetDueTime = dueTime ?? (isResolved ? resolvedTime! : nowMs);
              const effectiveElapsedEnd = isResolved
                ? Math.min(resolvedTime!, targetDueTime)
                : isPaused && pausedTime
                ? Math.min(pausedTime, targetDueTime)
                : Math.min(nowMs, targetDueTime);

              // Overlapping on-track elapsed part
              const visElapsedStartMs = Math.max(createdTime, windowStart);
              const visElapsedEndMs = Math.min(effectiveElapsedEnd, windowEnd);
              const hasElapsedBar =
                !isResolvedBeforeWindow &&
                !isEntirelyAfterWindow &&
                visElapsedEndMs > visElapsedStartMs;

              const xStartElapsed = hasElapsedBar
                ? LABEL_WIDTH + mapTimeToPosition(visElapsedStartMs, windowData).x
                : 0;
              const xEndElapsed = hasElapsedBar
                ? LABEL_WIDTH + mapTimeToPosition(visElapsedEndMs, windowData).x
                : 0;

              // Overlapping remaining hollow part
              const remainingStartMs = Math.max(createdTime, nowMs);
              const visRemainingStartMs = Math.max(remainingStartMs, windowStart);
              const visRemainingEndMs = Math.min(targetDueTime, windowEnd);
              const hasRemainingBar =
                !isResolved &&
                !isEntirelyAfterWindow &&
                nowMs < targetDueTime &&
                visRemainingEndMs > visRemainingStartMs;

              const xStartRemaining = hasRemainingBar
                ? LABEL_WIDTH + mapTimeToPosition(visRemainingStartMs, windowData).x
                : 0;
              const xEndRemaining = hasRemainingBar
                ? LABEL_WIDTH + mapTimeToPosition(visRemainingEndMs, windowData).x
                : 0;

              // Overdue stretch interval: [targetDueTime, nowMs] (or [targetDueTime, resolvedTime])
              const overdueActiveEnd = isResolved ? resolvedTime! : nowMs;
              const isOverdueHappening =
                dueTime !== null &&
                overdueActiveEnd > dueTime &&
                (ticket.is_overdue || overdueActiveEnd > dueTime);

              const visOverdueStartMs = isOverdueHappening ? Math.max(dueTime!, windowStart) : 0;
              const visOverdueEndMs = isOverdueHappening ? Math.min(overdueActiveEnd, windowEnd) : 0;
              const hasOverdueStretch =
                !isResolvedBeforeWindow &&
                !isEntirelyAfterWindow &&
                isOverdueHappening &&
                visOverdueEndMs > visOverdueStartMs;

              const xStartOverdue = hasOverdueStretch
                ? LABEL_WIDTH + mapTimeToPosition(visOverdueStartMs, windowData).x
                : 0;
              const xEndOverdue = hasOverdueStretch
                ? LABEL_WIDTH + mapTimeToPosition(visOverdueEndMs, windowData).x
                : 0;

              // Left clip marker: created before window and not resolved before window
              const showLeftClipMarker = createdTime < windowStart && !isResolvedBeforeWindow;

              // Right clip marker: life continues after window
              const showRightClipMarker = isEntirelyAfterWindow;

              // Diamond SLA target: due date is inside visible window
              const showDiamond =
                dueTime !== null &&
                dueTime >= windowStart &&
                dueTime <= windowEnd &&
                !isResolvedBeforeWindow;
              const xDiamond = showDiamond
                ? LABEL_WIDTH + mapTimeToPosition(dueTime!, windowData).x
                : 0;

              return (
                <g
                  key={ticket.id}
                  tabIndex={0}
                  role="link"
                  aria-label={`Ticket #${ticket.id}: ${ticket.title}. Status: ${ticket.status}, Priority: ${ticket.priority}, SLA: ${sla.label}`}
                  className="cursor-pointer focus:outline-none"
                  onClick={() => navigate(`/tickets/${ticket.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate(`/tickets/${ticket.id}`);
                    }
                  }}
                  onMouseEnter={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    setHoveredTicket({
                      ticket,
                      sla,
                      x: rect.left + 290,
                      y: rect.top,
                    });
                  }}
                  onMouseLeave={() => setHoveredTicket(null)}
                  onFocus={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    setHoveredTicket({
                      ticket,
                      sla,
                      x: rect.left + 290,
                      y: rect.top,
                    });
                  }}
                  onBlur={() => setHoveredTicket(null)}
                >
                  {/* Row background */}
                  <rect
                    x={0}
                    y={rowY}
                    width={totalSvgWidth}
                    height={ROW_HEIGHT}
                    fill={isFocusedOrHovered ? '#F2EDE3' : isEven ? '#FBF8F3' : '#F7F3EA'}
                    opacity={isFocusedOrHovered ? 0.9 : 0.6}
                  />

                  {/* Horizontal row separator */}
                  <line
                    x1={0}
                    y1={rowY + ROW_HEIGHT}
                    x2={totalSvgWidth}
                    y2={rowY + ROW_HEIGHT}
                    stroke="#E4DED2"
                    strokeWidth="1"
                  />

                  {/* Left Label Area */}
                  {/* First line: Ticket ID + Title with tooltip */}
                  <text
                    x={12}
                    y={rowY + 19}
                    fill="#1F2937"
                    fontFamily="monospace"
                    fontSize="11"
                    fontWeight="600"
                  >
                    #{ticket.id}
                  </text>

                  <text
                    x={48}
                    y={rowY + 19}
                    fill="#1F2937"
                    fontSize="12"
                    fontWeight="500"
                  >
                    <title>{ticket.title}</title>
                    {ticket.title.length > 27 ? `${ticket.title.slice(0, 26)}…` : ticket.title}
                  </text>

                  {/* Second line: Status pill (with Runway colors) + Assignee/Priority */}
                  <g className="status-pill" data-testid={`status-pill-${ticket.status}`}>
                    <rect
                      x={12}
                      y={rowY + 28}
                      width={pill.width}
                      height={16}
                      rx={3}
                      fill={pill.bg}
                      stroke={pill.stroke}
                      strokeWidth="1"
                    />
                    <text
                      x={12 + pill.width / 2}
                      y={rowY + 40}
                      textAnchor="middle"
                      fill={pill.text}
                      fontSize="9.5"
                      fontWeight="600"
                    >
                      {pill.label}
                    </text>
                  </g>

                  <text
                    x={12 + pill.width + 8}
                    y={rowY + 40}
                    fill="#6B7280"
                    fontSize="10"
                  >
                    {isStaff && ticket.assignee_name ? `${ticket.assignee_name} · ` : ''}
                    {ticket.priority.charAt(0).toUpperCase() + ticket.priority.slice(1)}
                  </text>

                  {/* TIMELINE CHART AREA */}
                  {/* Track guide line */}
                  <line
                    x1={trackStartX}
                    y1={centerY}
                    x2={trackEndX}
                    y2={centerY}
                    stroke="#E4DED2"
                    strokeWidth="1.5"
                    strokeDasharray="2,2"
                  />

                  {/* Case A: Resolved before window started -> show small grey text */}
                  {isResolvedBeforeWindow && (
                    <text
                      x={trackStartX + 12}
                      y={centerY + 4}
                      fill="#6B7280"
                      fontSize="11"
                      fontStyle="italic"
                    >
                      resolved {formatKolkataShortDate(ticket.resolved_at || ticket.updated_at)}
                    </text>
                  )}

                  {/* Case B: Overdue hatched coral stretch (drawn from due date or left edge up to NOW / right edge) */}
                  {hasOverdueStretch && (
                    <g className="overdue-stretch" data-testid="overdue-stretch">
                      <rect
                        x={xStartOverdue}
                        y={barY}
                        width={Math.max(2, xEndOverdue - xStartOverdue)}
                        height={barHeight}
                        rx={3}
                        fill="#E4572E"
                        fillOpacity="0.15"
                      />
                      <rect
                        x={xStartOverdue}
                        y={barY}
                        width={Math.max(2, xEndOverdue - xStartOverdue)}
                        height={barHeight}
                        rx={3}
                        fill={`url(#${overduePatternId})`}
                        opacity="0.8"
                      />
                      <rect
                        x={xStartOverdue}
                        y={barY}
                        width={Math.max(2, xEndOverdue - xStartOverdue)}
                        height={barHeight}
                        rx={3}
                        fill="none"
                        stroke="#E4572E"
                        strokeWidth="1"
                      />
                    </g>
                  )}

                  {/* Case C: On-track elapsed SLA bar */}
                  {hasElapsedBar && (
                    <rect
                      data-testid="elapsed-bar"
                      x={xStartElapsed}
                      y={barY}
                      width={Math.max(2, xEndElapsed - xStartElapsed)}
                      height={barHeight}
                      rx={3}
                      fill={sla.colorHex}
                      opacity={isResolved ? 0.6 : 0.9}
                    />
                  )}

                  {/* Case D: Remaining SLA bar (hollow outline) */}
                  {hasRemainingBar && (
                    <rect
                      data-testid="remaining-bar"
                      x={xStartRemaining}
                      y={barY}
                      width={Math.max(2, xEndRemaining - xStartRemaining)}
                      height={barHeight}
                      rx={3}
                      fill="none"
                      stroke={sla.colorHex}
                      strokeWidth="1.5"
                      strokeDasharray="3,2"
                      opacity="0.8"
                    />
                  )}

                  {/* Left clipping indicator (<) if created earlier than window */}
                  {showLeftClipMarker && (
                    <g
                      transform={`translate(${trackStartX + 3}, ${centerY})`}
                      aria-label="Created before window"
                      data-testid="clip-left-marker"
                    >
                      <polygon points="5,-4 0,0 5,4" fill="#6B7280" />
                    </g>
                  )}

                  {/* Right clipping indicator (>) if created after window */}
                  {showRightClipMarker && (
                    <g
                      transform={`translate(${trackEndX - 8}, ${centerY})`}
                      aria-label="Created after window"
                      data-testid="clip-right-marker"
                    >
                      <polygon points="-5,-4 0,0 -5,4" fill="#6B7280" />
                    </g>
                  )}

                  {/* SLA Due Diamond marker */}
                  {showDiamond && (
                    <polygon
                      data-testid="due-diamond"
                      points={`${xDiamond},${centerY - 5} ${xDiamond + 5},${centerY} ${xDiamond},${centerY + 5} ${xDiamond - 5},${centerY}`}
                      fill={sla.colorHex}
                      stroke="#FBF8F3"
                      strokeWidth="1.5"
                    />
                  )}
                </g>
              );
            })
          )}

          {/* Vertical NOW Line */}
          {!nowPos.isClippedLeft && !nowPos.isClippedRight && (
            <g transform={`translate(${LABEL_WIDTH + nowPos.x}, 0)`}>
              {/* Vertical red line */}
              <line
                x1={0}
                y1={HEADER_HEIGHT}
                x2={0}
                y2={totalSvgHeight}
                stroke="#E4572E"
                strokeWidth="1.5"
                strokeDasharray="4,2"
              />
              {/* NOW tag at top */}
              <rect x={-18} y={HEADER_HEIGHT - 18} width={36} height={16} rx={3} fill="#E4572E" />
              <text
                x={0}
                y={HEADER_HEIGHT - 6}
                textAnchor="middle"
                fill="#FFFFFF"
                fontSize="9"
                fontWeight="700"
                fontFamily="sans-serif"
              >
                NOW
              </text>
            </g>
          )}
        </svg>

        {/* Hover / Focus Tooltip (Fixed/Absolute Overlay) */}
        {hoveredTicket && (
          <div
            className="absolute z-20 pointer-events-none bg-paper border border-line shadow-md rounded p-3 text-xs text-ink max-w-xs"
            style={{
              top: Math.max(10, hoveredTicket.y - 120),
              left: Math.min(window.innerWidth - 300, hoveredTicket.x),
            }}
          >
            <div className="font-serif font-bold text-sm mb-1 text-ink">
              #{hoveredTicket.ticket.id} {hoveredTicket.ticket.title}
            </div>
            <div className="flex items-center gap-2 mb-2">
              <span
                className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium"
                style={{
                  backgroundColor: hoveredTicket.sla.bgHex,
                  color: hoveredTicket.sla.colorHex,
                }}
              >
                {hoveredTicket.sla.label}
              </span>
              <span className="text-muted capitalize">
                {hoveredTicket.ticket.status.replace(/_/g, ' ')}
              </span>
              <span className="text-muted capitalize">
                {hoveredTicket.ticket.priority} priority
              </span>
            </div>
            <div className="space-y-0.5 text-[11px] border-t border-line/50 pt-1.5 text-muted">
              <div>
                <span className="font-medium text-ink">Created:</span>{' '}
                {formatKolkataDateTime(hoveredTicket.ticket.created_at)}
              </div>
              <div>
                <span className="font-medium text-ink">SLA Due:</span>{' '}
                {hoveredTicket.ticket.due_at
                  ? formatKolkataDateTime(hoveredTicket.ticket.due_at)
                  : 'No SLA'}
              </div>
              <div>
                <span className="font-medium text-ink">Remaining:</span>{' '}
                {hoveredTicket.ticket.due_at
                  ? formatDurationShort(
                      computeBusinessMinutesRemaining(hoveredTicket.ticket.due_at)
                    )
                  : 'N/A'}
              </div>
              {hoveredTicket.ticket.assignee_name && isStaff && (
                <div>
                  <span className="font-medium text-ink">Assignee:</span>{' '}
                  {hoveredTicket.ticket.assignee_name}
                </div>
              )}
              {hoveredTicket.ticket.requester_name && (
                <div>
                  <span className="font-medium text-ink">Requester:</span>{' '}
                  {hoveredTicket.ticket.requester_name}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 py-2 px-3 bg-paper2 border border-line rounded-lg text-xs text-muted">
        <span className="font-serif font-semibold text-ink">Legend:</span>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-teal inline-block" />
          <span>On track (&lt;75% SLA elapsed)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-amber inline-block" />
          <span>At risk (≥75% elapsed)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded border border-coral inline-block"
            style={{
              background: 'repeating-linear-gradient(45deg, #E4572E, #E4572E 2px, transparent 2px, transparent 4px)',
            }}
          />
          <span>Overdue stretch</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-purple inline-block" />
          <span>Clock paused (waiting on requester)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <svg width="10" height="10" viewBox="0 0 10 10" className="inline-block">
            <polygon points="5,0 10,5 5,10 0,5" fill="#0F766E" />
          </svg>
          <span>SLA target</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-coral inline-block" />
          <span>NOW (current Kolkata time)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 border border-line bg-line/40 inline-block" />
          <span>Weekend (SLA paused)</span>
        </div>
      </div>
    </div>
  );
};
