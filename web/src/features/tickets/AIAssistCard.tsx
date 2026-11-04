import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/useAuth';
import { getAIAssistStatus, requestAIAssist } from '../../api/client';
import type {
  AIAssistStatusResponse,
  AIAssistSummaryResponse,
  AIAssistReplyResponse,
} from '../../api/types';

export interface AIAssistCardProps {
  ticketId: number;
  onInsertReply: (draftText: string) => void;
}

export const AIAssistCard: React.FC<AIAssistCardProps> = ({ ticketId, onInsertReply }) => {
  const { user } = useAuth();
  const isStaff = user?.role === 'agent' || user?.role === 'admin';

  const [status, setStatus] = useState<AIAssistStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(Boolean(isStaff));
  const [activeTask, setActiveTask] = useState<'summary' | 'reply' | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryData, setSummaryData] = useState<AIAssistSummaryResponse | null>(null);
  const [replyData, setReplyData] = useState<AIAssistReplyResponse | null>(null);
  const [insertedNotice, setInsertedNotice] = useState(false);

  useEffect(() => {
    let ignore = false;
    if (!isStaff) {
      return;
    }

    getAIAssistStatus()
      .then((res) => {
        if (!ignore) {
          setStatus(res);
          setStatusLoading(false);
        }
      })
      .catch(() => {
        if (!ignore) {
          setStatus({ enabled: false, mode: 'off', model: null });
          setStatusLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [isStaff]);

  if (!isStaff || statusLoading) {
    return null;
  }

  // Disabled state
  if (!status || !status.enabled) {
    return (
      <div
        data-testid="ai-assist-card-disabled"
        className="bg-paper border border-dashed border-line rounded-lg p-4 flex items-center justify-between gap-4 text-muted text-sm shadow-xs"
      >
        <div className="flex items-center gap-2.5">
          <span className="font-semibold text-ink text-sm">AI Assist</span>
          <span className="text-xs font-mono uppercase px-1.5 py-0.5 rounded bg-paper2 border border-line text-muted">
            Off
          </span>
        </div>
        <p className="text-xs text-muted">
          AI assist is disabled on this server. Enable with <code className="font-mono bg-paper2 px-1 rounded">AI_ASSIST_MODE=ollama</code>.
        </p>
      </div>
    );
  }

  const handleRunTask = async (task: 'summary' | 'reply') => {
    setLoading(true);
    setError(null);
    setActiveTask(task);
    setInsertedNotice(false);

    try {
      const res = await requestAIAssist(ticketId, task);
      if (res.task === 'summary') {
        setSummaryData(res as AIAssistSummaryResponse);
      } else {
        setReplyData(res as AIAssistReplyResponse);
      }
    } catch (err: unknown) {
      let msg = 'AI assist is currently unavailable. Ensure Ollama is running locally.';
      if (err && typeof err === 'object' && 'message' in err && typeof (err as { message: string }).message === 'string') {
        const errMsg = (err as { message: string }).message;
        if (errMsg && !errMsg.startsWith('HTTP 502')) {
          msg = errMsg;
        }
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleInsert = () => {
    if (replyData?.reply) {
      onInsertReply(replyData.reply);
      setInsertedNotice(true);
      setTimeout(() => setInsertedNotice(false), 2500);
    }
  };

  return (
    <div
      data-testid="ai-assist-card"
      className="bg-paper border border-line rounded-lg p-5 flex flex-col gap-4 shadow-xs"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <svg
            className="w-4 h-4 text-teal"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
          </svg>
          <span className="font-semibold text-sm text-ink">AI Assist</span>
          {status.model && (
            <span
              data-testid="ai-assist-model-badge"
              className="text-xs font-mono px-2 py-0.5 rounded bg-paper2 border border-line text-muted"
            >
              {status.model}
            </span>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleRunTask('summary')}
            disabled={loading}
            className={`px-3 py-1.5 text-xs font-medium rounded border transition-colors shadow-xs ${
              activeTask === 'summary' && !loading
                ? 'bg-paper2 border-teal text-ink font-semibold'
                : 'bg-white border-line text-ink hover:bg-paper2'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            Summarize
          </button>
          <button
            type="button"
            onClick={() => handleRunTask('reply')}
            disabled={loading}
            className={`px-3 py-1.5 text-xs font-medium rounded border transition-colors shadow-xs ${
              activeTask === 'reply' && !loading
                ? 'bg-paper2 border-teal text-ink font-semibold'
                : 'bg-white border-line text-ink hover:bg-paper2'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            Draft reply
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div
          role="status"
          className="flex items-center gap-3 p-3 bg-paper2/60 border border-line rounded text-xs text-muted"
        >
          <svg className="animate-spin h-4 w-4 text-teal shrink-0" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          <span>Generating… (cold start can take ~15s on first run)</span>
        </div>
      )}

      {/* Error state */}
      {error && !loading && (
        <div
          role="alert"
          className="p-3 bg-coral/10 border border-coral/30 rounded text-xs text-coral flex items-center justify-between gap-2"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-coral hover:underline shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Summary Output */}
      {activeTask === 'summary' && summaryData && !loading && (
        <div className="flex flex-col gap-3 pt-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">
              Issue Summary
            </span>
            <span className="text-xs font-mono text-muted">
              Generated in {(summaryData.latency_ms / 1000).toFixed(1)}s
            </span>
          </div>

          <div className="p-3 bg-paper2/50 border border-line rounded text-sm text-ink whitespace-pre-wrap leading-relaxed">
            {summaryData.summary}
          </div>

          {summaryData.facts && summaryData.facts.length > 0 && (
            <div className="flex flex-col gap-1.5 mt-1">
              <span className="text-xs font-mono text-muted uppercase tracking-wider">
                Key Facts
              </span>
              <div className="flex flex-wrap gap-2">
                {summaryData.facts.map((fact, idx) => (
                  <div
                    key={idx}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-white border border-line text-xs shadow-xs"
                  >
                    <span className="font-semibold text-muted uppercase font-mono text-[10px]">
                      {fact.label}:
                    </span>
                    <span className="text-ink font-medium">{fact.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Reply Output */}
      {activeTask === 'reply' && replyData && !loading && (
        <div className="flex flex-col gap-3 pt-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">
                Draft Reply
              </span>
              <span className="text-xs px-2 py-0.5 rounded font-medium bg-amber/10 border border-amber/30 text-amber">
                Draft only. Review before posting.
              </span>
            </div>
            <span className="text-xs font-mono text-muted">
              Generated in {(replyData.latency_ms / 1000).toFixed(1)}s
            </span>
          </div>

          <div className="p-3 bg-paper2/50 border border-line rounded text-sm text-ink whitespace-pre-wrap leading-relaxed font-sans">
            {replyData.reply}
          </div>

          <div className="flex items-center justify-between gap-3 pt-1">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleInsert}
                className="px-3 py-1.5 text-xs font-medium text-white bg-teal hover:bg-teal/90 rounded transition-colors shadow-xs"
              >
                Insert into reply
              </button>
              <button
                type="button"
                onClick={() => handleRunTask('reply')}
                className="px-3 py-1.5 text-xs font-medium text-ink bg-white border border-line hover:bg-paper2 rounded transition-colors shadow-xs"
              >
                Regenerate
              </button>
            </div>
            {insertedNotice && (
              <span className="text-xs font-semibold text-teal animate-fade-in">
                Inserted into composer!
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
