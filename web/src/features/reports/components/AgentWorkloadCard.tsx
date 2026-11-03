import React from 'react';
import { ReportCard } from './ReportCard';
import type {
  AgentRankingItem,
  AgentWorkloadItem,
  ResolutionTimeItem,
} from '../../../api/reports';
import { mergeAgents, type MergedAgentRow } from '../reportData';

export interface AgentWorkloadCardProps {
  ranking: AgentRankingItem[] | null;
  workload: AgentWorkloadItem[] | null;
  resolution: ResolutionTimeItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export const AgentWorkloadCard: React.FC<AgentWorkloadCardProps> = ({
  ranking,
  workload,
  resolution,
  loading,
  error,
  onRetry,
}) => {
  const rows: MergedAgentRow[] = React.useMemo(() => {
    if (!ranking && !workload && !resolution) return [];
    return mergeAgents(ranking || [], workload || [], resolution || []);
  }, [ranking, workload, resolution]);

  const isEmpty = rows.length === 0;

  return (
    <ReportCard
      title="Agent workload"
      subtitle="Performance rankings, active workload, overdue counts, and resolution velocity"
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={isEmpty}
      emptyMessage="No agents found"
      hasTableView={false}
    >
      <div className="overflow-x-auto max-h-96">
        <table
          className="w-full text-left text-xs border-collapse"
          aria-label="Agent workload and performance ranking table"
        >
          <thead>
            <tr className="border-b border-line text-muted font-medium bg-paper2/50">
              <th className="py-2.5 px-3 w-12 text-center">Rank</th>
              <th className="py-2.5 px-3">Agent</th>
              <th className="py-2.5 px-3 text-right">Open</th>
              <th className="py-2.5 px-3 text-right">Overdue</th>
              <th className="py-2.5 px-3 text-right">Resolved</th>
              <th className="py-2.5 px-3 text-right">Avg Hours</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((agent) => {
              const initial = agent.agent_name.trim().charAt(0).toUpperCase() || 'A';
              const isOverduePositive =
                typeof agent.overdue_tickets === 'number' && agent.overdue_tickets > 0;

              return (
                <tr
                  key={agent.agent_id}
                  className="border-b border-line/60 hover:bg-paper2/40 transition-colors"
                >
                  {/* Rank */}
                  <td className="py-2.5 px-3 text-center font-mono font-medium text-muted">
                    {agent.rank !== '-' ? `#${agent.rank}` : '—'}
                  </td>

                  {/* Agent with avatar initial */}
                  <td className="py-2.5 px-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-6 h-6 rounded-full bg-teal/15 text-teal text-xs font-semibold flex items-center justify-center shrink-0 border border-teal/20"
                        aria-hidden="true"
                      >
                        {initial}
                      </div>
                      <span className="font-medium text-ink whitespace-nowrap">
                        {agent.agent_name}
                      </span>
                    </div>
                  </td>

                  {/* Open tickets */}
                  <td className="py-2.5 px-3 text-right font-medium text-ink font-mono">
                    {agent.open_tickets}
                  </td>

                  {/* Overdue tickets: coral pill when > 0 */}
                  <td className="py-2.5 px-3 text-right">
                    {isOverduePositive ? (
                      <span
                        className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-coral/15 text-coral border border-coral/30"
                        title={`${agent.overdue_tickets} overdue tickets`}
                      >
                        {agent.overdue_tickets}
                      </span>
                    ) : (
                      <span className="text-muted font-mono">{agent.overdue_tickets}</span>
                    )}
                  </td>

                  {/* Resolved tickets */}
                  <td className="py-2.5 px-3 text-right font-medium text-teal font-mono">
                    {agent.resolved_tickets}
                  </td>

                  {/* Average hours */}
                  <td className="py-2.5 px-3 text-right font-mono text-muted">
                    {typeof agent.avg_resolution_hours === 'number'
                      ? `${agent.avg_resolution_hours.toFixed(1)}h`
                      : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ReportCard>
  );
};

