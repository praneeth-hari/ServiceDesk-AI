import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import { ApiError, getDemoAccounts, demoLogin as apiDemoLogin } from '../api/client';
import type { DemoAccountsResponse, RateLimitErrorData } from '../api/types';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Rate limiting lockout state
  const [retryAfter, setRetryAfter] = useState<number | null>(null);

  // Demo mode state
  const [demoAccounts, setDemoAccounts] = useState<DemoAccountsResponse | null>(null);
  const [demoLoading, setDemoLoading] = useState<string | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);

  const { login, demoLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/tickets';

  // Fetch demo accounts on mount. If disabled or fails, show nothing extra.
  useEffect(() => {
    let ignore = false;
    const fetchDemo = async () => {
      try {
        const res = await getDemoAccounts();
        if (!ignore && res && res.enabled) {
          setDemoAccounts(res);
        }
      } catch {
        // Silently ignore if demo accounts call fails or demo mode is off
      }
    };
    fetchDemo();
    return () => {
      ignore = true;
    };
  }, []);

  // Live countdown timer for rate limiting lockout
  useEffect(() => {
    if (retryAfter === null || retryAfter <= 0) return;

    const timer = setInterval(() => {
      setRetryAfter((prev) => {
        if (prev === null || prev <= 1) {
          clearInterval(timer);
          return null;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [retryAfter]);

  const formatCountdown = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (retryAfter !== null && retryAfter > 0) return;

    setError(null);
    setLoading(true);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        const data = err.data as RateLimitErrorData | undefined;
        const retrySec = data?.retry_after_seconds ?? 300;
        setRetryAfter(retrySec);
        setError(null);
      } else if (err instanceof ApiError && err.status === 401) {
        setError('Invalid email or password.');
      } else if (
        (err instanceof ApiError && err.status >= 500) ||
        !(err instanceof ApiError)
      ) {
        setError('Cannot reach the server. Please try again.');
      } else if (err instanceof Error) {
        setError(err.message || 'An unexpected error occurred.');
      } else {
        setError('Cannot reach the server. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDemoLogin = async (role: 'requester' | 'agent' | 'admin') => {
    setDemoError(null);
    setDemoLoading(role);

    try {
      if (demoLogin) {
        await demoLogin(role);
      } else {
        await apiDemoLogin(role);
      }
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setDemoError('Demo accounts not found. Please run seed_demo to create sample accounts.');
      } else if (err instanceof Error) {
        setDemoError(err.message || 'Failed to sign in with demo account.');
      } else {
        setDemoError('Failed to sign in with demo account.');
      }
    } finally {
      setDemoLoading(null);
    }
  };

  const isPaused = retryAfter !== null && retryAfter > 0;

  return (
    <div className="min-h-screen grid grid-cols-1 md:grid-cols-2 bg-paper text-ink font-sans">
      {/* Left panel */}
      <div className="bg-paper2 border-r border-line p-8 md:p-12 lg:p-16 flex flex-col justify-between">
        <div>
          <span className="font-serif text-3xl font-bold tracking-tight text-ink block">
            Runway
          </span>
          <p className="font-serif italic text-lg text-ink/80 mt-3">
            See every SLA, counted in business hours.
          </p>

          {/* Decorative SLA / business hours SVG illustration */}
          <div className="mt-8 max-w-md">
            <svg
              viewBox="0 0 400 220"
              className="w-full h-auto rounded border border-line bg-paper"
              aria-label="Illustration of business hours SLA clock paused on weekend"
              role="img"
            >
              <defs>
                <pattern
                  id="weekendHatch"
                  width="8"
                  height="8"
                  patternTransform="rotate(45 0 0)"
                  patternUnits="userSpaceOnUse"
                >
                  <line x1="0" y1="0" x2="0" y2="8" stroke="#E4DED2" strokeWidth="2" />
                </pattern>
              </defs>

              {/* Day column headers */}
              <text x="35" y="24" fill="#6B7280" fontSize="11" fontFamily="sans-serif">Thu</text>
              <text x="110" y="24" fill="#6B7280" fontSize="11" fontFamily="sans-serif">Fri</text>
              <text x="195" y="24" fill="#6B7280" fontSize="11" fontFamily="sans-serif">Sat</text>
              <text x="270" y="24" fill="#6B7280" fontSize="11" fontFamily="sans-serif">Sun</text>
              <text x="350" y="24" fill="#6B7280" fontSize="11" fontFamily="sans-serif">Mon</text>

              <line x1="80" y1="32" x2="80" y2="200" stroke="#E4DED2" strokeDasharray="3 3" />
              <line x1="160" y1="32" x2="160" y2="200" stroke="#E4DED2" strokeDasharray="3 3" />
              <line x1="320" y1="32" x2="320" y2="200" stroke="#E4DED2" strokeDasharray="3 3" />

              {/* Hatched vertical weekend band (Sat-Sun) */}
              <rect x="160" y="32" width="160" height="168" fill="url(#weekendHatch)" />
              <rect x="160" y="32" width="160" height="168" fill="#F2EDE3" opacity="0.3" />
              <text
                x="240"
                y="120"
                fill="#6B7280"
                fontSize="10"
                fontFamily="sans-serif"
                textAnchor="middle"
                letterSpacing="1"
              >
                WEEKEND PAUSE
              </text>

              {/* Three horizontal bars (teal/amber) */}
              <rect x="30" y="56" width="110" height="14" rx="2" fill="#0F766E" />
              <rect x="320" y="56" width="50" height="14" rx="2" fill="#99D2CB" />
              <rect x="40" y="94" width="75" height="14" rx="2" fill="#D99A00" />
              <rect x="20" y="146" width="95" height="14" rx="2" fill="#0F766E" opacity="0.8" />

              {/* Coral vertical NOW line with small label */}
              <line x1="125" y1="32" x2="125" y2="200" stroke="#E4572E" strokeWidth="2" />
              <rect x="110" y="8" width="30" height="16" rx="2" fill="#E4572E" />
              <text
                x="125"
                y="20"
                fill="#FFFFFF"
                fontSize="9"
                fontWeight="bold"
                fontFamily="monospace"
                textAnchor="middle"
              >
                NOW
              </text>
            </svg>
          </div>
        </div>

        <div className="pt-8 text-xs text-muted">
          ServiceDesk-AI &bull; IT Support Platform
        </div>
      </div>

      {/* Right panel (form) */}
      <div className="flex items-center justify-center p-8 md:p-12 lg:p-16 bg-paper">
        <div className="w-full max-w-sm">
          <h1 className="font-serif text-3xl font-semibold text-ink mb-6">
            Sign in
          </h1>

          {/* Rate limiting amber pause notice */}
          {isPaused && (
            <div
              role="status"
              className="mb-4 p-3 rounded bg-amber-500/10 border border-amber-500/30 text-ink text-sm flex items-start gap-2"
            >
              <div>
                Too many sign-in attempts. For safety, sign-in is paused for this email and device. Try again in {formatCountdown(retryAfter)}.
              </div>
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="mb-4 p-3 rounded bg-coral/10 border border-coral/30 text-coral text-sm"
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-ink mb-1"
              >
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="agent@example.com"
                className="w-full px-3 py-2 bg-paper border border-line rounded text-sm text-ink placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-teal focus:border-transparent transition-all"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-ink mb-1"
              >
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 bg-paper border border-line rounded text-sm text-ink placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-teal focus:border-transparent transition-all"
              />
            </div>

            <button
              type="submit"
              disabled={loading || isPaused}
              className="w-full py-2.5 px-4 bg-teal hover:bg-teal/90 text-white font-medium rounded text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-teal focus:ring-offset-2 disabled:opacity-50 flex items-center justify-center cursor-pointer disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="inline-flex items-center">
                  <svg
                    className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8v8H4z"
                    />
                  </svg>
                  Signing in...
                </span>
              ) : isPaused ? (
                'Sign in (paused)'
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          {/* Demo accounts section (shown only when DEMO_MODE is true) */}
          {demoAccounts && demoAccounts.enabled && demoAccounts.accounts.length > 0 && (
            <div className="mt-8 pt-6 border-t border-line space-y-4">
              <div className="relative flex items-center justify-center">
                <span className="bg-paper px-2 text-xs text-muted uppercase tracking-wider font-medium">
                  or try a demo account
                </span>
              </div>

              {demoError && (
                <div
                  role="alert"
                  className="p-3 rounded bg-coral/10 border border-coral/30 text-coral text-xs"
                >
                  {demoError}
                </div>
              )}

              <div className="space-y-2">
                {demoAccounts.accounts.map((acc) => (
                  <button
                    key={acc.role}
                    type="button"
                    onClick={() => handleDemoLogin(acc.role)}
                    disabled={demoLoading !== null}
                    className="w-full text-left p-3 rounded border border-line bg-paper2/40 hover:bg-paper2 transition-colors focus:outline-none focus:ring-2 focus:ring-teal flex flex-col gap-1 disabled:opacity-50 cursor-pointer"
                    aria-label={`Demo sign in as ${acc.name} (${acc.role})`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm text-ink">{acc.name}</span>
                      <span className="text-[10px] font-mono uppercase tracking-wider font-semibold px-2 py-0.5 rounded border border-line bg-paper text-ink">
                        {acc.role}
                      </span>
                    </div>
                    <p className="text-xs text-muted">{acc.description}</p>
                  </button>
                ))}
              </div>

              <p className="text-xs text-muted text-center pt-1">
                Demo mode is on. Public demo only: accounts hold sample data.
              </p>
            </div>
          )}

          {(!demoAccounts || !demoAccounts.enabled) && (
            <p className="text-xs text-muted text-center mt-6">
              Demo accounts work on local installs only
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
