import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  getTicketsByStatus,
  getOverdueTickets,
  getResolutionTime,
  getAgentRanking,
  getDailyVolume,
  getSLABreachRate,
  getResolutionTimeByCategory,
  getAgentWorkload,
  getTicketsByCategory,
  type TicketsByStatusItem,
  type OverdueTicketItem,
  type ResolutionTimeItem,
  type AgentRankingItem,
  type DailyVolumeItem,
  type SLABreachRateItem,
  type ResolutionTimeByCategoryItem,
  type AgentWorkloadItem,
  type TicketsByCategoryItem,
} from '../../api/reports';
import { kpis } from './reportData';
import { StatTiles } from './components/StatTiles';
import { DailyVolumeCard } from './components/DailyVolumeCard';
import { StatusPriorityCard } from './components/StatusPriorityCard';
import { CategoryCard } from './components/CategoryCard';
import { SlaCard } from './components/SlaCard';
import { ResolutionTimeCard } from './components/ResolutionTimeCard';
import { AgentWorkloadCard } from './components/AgentWorkloadCard';
import { OverdueCard } from './components/OverdueCard';

export const ReportsPage: React.FC = () => {
  // 1. Tickets By Status
  const [statusItems, setStatusItems] = useState<TicketsByStatusItem[] | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusKey, setStatusKey] = useState(0);

  const retryTicketsByStatus = useCallback(() => {
    setStatusLoading(true);
    setStatusKey((k) => k + 1);
  }, []);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getTicketsByStatus();
        if (!ignore) {
          setStatusItems(data);
          setStatusError(null);
        }
      } catch {
        if (!ignore) {
          setStatusError('Failed to load tickets by status');
        }
      } finally {
        if (!ignore) {
          setStatusLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [statusKey]);

  // 2. Overdue Tickets
  const [overdueItems, setOverdueItems] = useState<OverdueTicketItem[] | null>(null);
  const [overdueLoading, setOverdueLoading] = useState(true);
  const [overdueError, setOverdueError] = useState<string | null>(null);
  const [overdueKey, setOverdueKey] = useState(0);

  const retryOverdue = useCallback(() => {
    setOverdueLoading(true);
    setOverdueKey((k) => k + 1);
  }, []);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getOverdueTickets();
        if (!ignore) {
          setOverdueItems(data);
          setOverdueError(null);
        }
      } catch {
        if (!ignore) {
          setOverdueError('Failed to load overdue tickets');
        }
      } finally {
        if (!ignore) {
          setOverdueLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [overdueKey]);

  // 3. Resolution Time (per agent)
  const [resTimeItems, setResTimeItems] = useState<ResolutionTimeItem[] | null>(null);
  const [resTimeLoading, setResTimeLoading] = useState(true);
  const [resTimeError, setResTimeError] = useState<string | null>(null);
  const [resTimeKey, setResTimeKey] = useState(0);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getResolutionTime();
        if (!ignore) {
          setResTimeItems(data);
          setResTimeError(null);
        }
      } catch {
        if (!ignore) {
          setResTimeError('Failed to load resolution time');
        }
      } finally {
        if (!ignore) {
          setResTimeLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [resTimeKey]);

  // 4. Agent Ranking
  const [rankingItems, setRankingItems] = useState<AgentRankingItem[] | null>(null);
  const [rankingLoading, setRankingLoading] = useState(true);
  const [rankingError, setRankingError] = useState<string | null>(null);
  const [rankingKey, setRankingKey] = useState(0);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getAgentRanking();
        if (!ignore) {
          setRankingItems(data);
          setRankingError(null);
        }
      } catch {
        if (!ignore) {
          setRankingError('Failed to load agent rankings');
        }
      } finally {
        if (!ignore) {
          setRankingLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [rankingKey]);

  // 5. Daily Volume
  const [dailyDays, setDailyDays] = useState(30);
  const [dailyItems, setDailyItems] = useState<DailyVolumeItem[] | null>(null);
  const [dailyLoading, setDailyLoading] = useState(true);
  const [dailyError, setDailyError] = useState<string | null>(null);
  const [dailyKey, setDailyKey] = useState(0);

  const retryDaily = useCallback(() => {
    setDailyLoading(true);
    setDailyKey((k) => k + 1);
  }, []);

  const handleDailyDaysChange = useCallback((days: number) => {
    setDailyDays(days);
    setDailyLoading(true);
    setDailyKey((k) => k + 1);
  }, []);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getDailyVolume(dailyDays);
        if (!ignore) {
          setDailyItems(data);
          setDailyError(null);
        }
      } catch {
        if (!ignore) {
          setDailyError('Failed to load daily volume');
        }
      } finally {
        if (!ignore) {
          setDailyLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [dailyDays, dailyKey]);

  // 6. SLA Breach Rate
  const [slaItems, setSlaItems] = useState<SLABreachRateItem[] | null>(null);
  const [slaLoading, setSlaLoading] = useState(true);
  const [slaError, setSlaError] = useState<string | null>(null);
  const [slaKey, setSlaKey] = useState(0);

  const retrySLABreachRate = useCallback(() => {
    setSlaLoading(true);
    setSlaKey((k) => k + 1);
  }, []);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getSLABreachRate();
        if (!ignore) {
          setSlaItems(data);
          setSlaError(null);
        }
      } catch {
        if (!ignore) {
          setSlaError('Failed to load SLA breach rate');
        }
      } finally {
        if (!ignore) {
          setSlaLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [slaKey]);

  // 7. Resolution Time by Category
  const [resByCategoryItems, setResByCategoryItems] = useState<
    ResolutionTimeByCategoryItem[] | null
  >(null);
  const [resByCategoryLoading, setResByCategoryLoading] = useState(true);
  const [resByCategoryError, setResByCategoryError] = useState<string | null>(null);
  const [resByCategoryKey, setResByCategoryKey] = useState(0);

  const retryResByCategory = useCallback(() => {
    setResByCategoryLoading(true);
    setResByCategoryKey((k) => k + 1);
  }, []);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getResolutionTimeByCategory();
        if (!ignore) {
          setResByCategoryItems(data);
          setResByCategoryError(null);
        }
      } catch {
        if (!ignore) {
          setResByCategoryError('Failed to load resolution time by category');
        }
      } finally {
        if (!ignore) {
          setResByCategoryLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [resByCategoryKey]);

  // 8. Agent Workload
  const [workloadItems, setWorkloadItems] = useState<AgentWorkloadItem[] | null>(null);
  const [workloadLoading, setWorkloadLoading] = useState(true);
  const [workloadError, setWorkloadError] = useState<string | null>(null);
  const [workloadKey, setWorkloadKey] = useState(0);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getAgentWorkload();
        if (!ignore) {
          setWorkloadItems(data);
          setWorkloadError(null);
        }
      } catch {
        if (!ignore) {
          setWorkloadError('Failed to load agent workload');
        }
      } finally {
        if (!ignore) {
          setWorkloadLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [workloadKey]);

  // 9. Tickets by Category
  const [breakdownByStatus, setBreakdownByStatus] = useState(false);
  const [categoryItems, setCategoryItems] = useState<TicketsByCategoryItem[] | null>(null);
  const [categoryLoading, setCategoryLoading] = useState(true);
  const [categoryError, setCategoryError] = useState<string | null>(null);
  const [categoryKey, setCategoryKey] = useState(0);

  const handleBreakdownChange = useCallback((split: boolean) => {
    setBreakdownByStatus(split);
    setCategoryLoading(true);
    setCategoryKey((k) => k + 1);
  }, []);

  const retryCategory = useCallback(() => {
    setCategoryLoading(true);
    setCategoryKey((k) => k + 1);
  }, []);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const data = await getTicketsByCategory(breakdownByStatus);
        if (!ignore) {
          setCategoryItems(data);
          setCategoryError(null);
        }
      } catch {
        if (!ignore) {
          setCategoryError('Failed to load tickets by category');
        }
      } finally {
        if (!ignore) {
          setCategoryLoading(false);
        }
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [breakdownByStatus, categoryKey]);

  // High level KPIs
  const summary = useMemo(() => {
    return kpis(statusItems, overdueItems, slaItems);
  }, [statusItems, overdueItems, slaItems]);

  const kpisLoading = statusLoading && overdueLoading && slaLoading;

  // Agent Workload Card combination
  const agentCardLoading = rankingLoading || workloadLoading || resTimeLoading;
  const agentCardError = rankingError || workloadError || resTimeError;
  const handleAgentRetry = useCallback(() => {
    if (rankingError) {
      setRankingLoading(true);
      setRankingKey((k) => k + 1);
    }
    if (workloadError) {
      setWorkloadLoading(true);
      setWorkloadKey((k) => k + 1);
    }
    if (resTimeError) {
      setResTimeLoading(true);
      setResTimeKey((k) => k + 1);
    }
  }, [rankingError, workloadError, resTimeError]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Page Title & Muted Subtitle */}
      <div className="border-b border-line pb-4">
        <h1 className="font-serif text-3xl font-semibold text-ink">Reports</h1>
        <p className="text-muted text-xs sm:text-sm mt-1">
          Live figures from the database. Dates are in UTC. Hours are elapsed hours,
          not business hours.
        </p>
      </div>

      {/* 4 Stat Tiles */}
      <StatTiles summary={summary} loading={kpisLoading} />

      {/* Main Grid Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Card 1: Tickets Created per day */}
        <DailyVolumeCard
          items={dailyItems}
          days={dailyDays}
          onDaysChange={handleDailyDaysChange}
          loading={dailyLoading}
          error={dailyError}
          onRetry={retryDaily}
        />

        {/* Card 2: Tickets by status */}
        <StatusPriorityCard
          items={statusItems}
          loading={statusLoading}
          error={statusError}
          onRetry={retryTicketsByStatus}
        />

        {/* Card 3: By category */}
        <CategoryCard
          items={categoryItems}
          breakdownByStatus={breakdownByStatus}
          onBreakdownChange={handleBreakdownChange}
          loading={categoryLoading}
          error={categoryError}
          onRetry={retryCategory}
        />

        {/* Card 4: SLA by priority */}
        <SlaCard
          items={slaItems}
          loading={slaLoading}
          error={slaError}
          onRetry={retrySLABreachRate}
        />

        {/* Card 5: Hours to resolve */}
        <ResolutionTimeCard
          items={resByCategoryItems}
          loading={resByCategoryLoading}
          error={resByCategoryError}
          onRetry={retryResByCategory}
        />

        {/* Card 6: Agent workload */}
        <AgentWorkloadCard
          ranking={rankingItems}
          workload={workloadItems}
          resolution={resTimeItems}
          loading={agentCardLoading}
          error={agentCardError}
          onRetry={handleAgentRetry}
        />

        {/* Card 7: Overdue now (Full width) */}
        <OverdueCard
          items={overdueItems}
          loading={overdueLoading}
          error={overdueError}
          onRetry={retryOverdue}
        />
      </div>
    </div>
  );
};
