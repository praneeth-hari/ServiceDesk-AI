import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';

export const AppShell: React.FC = () => {
  const { user, role, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isStaff = role === 'agent' || role === 'admin';
  const isAdmin = role === 'admin';

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `inline-flex items-center px-1 pt-1 pb-2 border-b-2 text-sm font-medium transition-colors ${
      isActive
        ? 'border-teal text-teal font-semibold'
        : 'border-transparent text-muted hover:text-ink hover:border-line'
    }`;

  const mobileNavLinkClass = ({ isActive }: { isActive: boolean }) =>
    `block pl-3 pr-4 py-2 border-l-4 text-base font-medium ${
      isActive
        ? 'bg-paper2 border-teal text-teal font-semibold'
        : 'border-transparent text-muted hover:bg-paper2 hover:text-ink'
    }`;

  return (
    <div className="min-h-screen bg-paper text-ink flex flex-col font-sans">
      <header className="border-b border-line bg-paper sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <div className="flex items-center space-x-8">
              <NavLink to="/tickets" className="flex items-center space-x-2">
                <span className="font-serif text-2xl font-semibold tracking-tight text-ink">
                  Runway
                </span>
              </NavLink>
              <nav className="hidden sm:flex space-x-6 h-16 pt-3">
                <NavLink to="/tickets" end className={navLinkClass}>
                  Tickets
                </NavLink>
                <NavLink to="/tickets/new" className={navLinkClass}>
                  New ticket
                </NavLink>
                {isStaff && (
                  <NavLink to="/reports" className={navLinkClass}>
                    Reports
                  </NavLink>
                )}
                {isStaff && (
                  <NavLink to="/ai-quality" className={navLinkClass}>
                    AI quality
                  </NavLink>
                )}
                {isAdmin && (
                  <NavLink to="/holidays" className={navLinkClass}>
                    Holidays
                  </NavLink>
                )}
              </nav>
            </div>

            <div className="hidden sm:flex items-center space-x-4">
              <div className="flex items-center space-x-3 bg-paper2 px-3 py-1.5 rounded border border-line text-xs">
                <span className="font-medium text-ink">{user?.full_name || user?.email}</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider bg-paper text-muted border border-line">
                  {role}
                </span>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="text-muted hover:text-coral transition-colors ml-2 font-medium"
                >
                  Sign out
                </button>
              </div>
            </div>

            <div className="flex sm:hidden items-center">
              <button
                type="button"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                aria-label="Toggle navigation"
                className="p-2 text-muted hover:text-ink focus:outline-none focus:ring-1 focus:ring-teal rounded"
              >
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {mobileMenuOpen ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  )}
                </svg>
              </button>
            </div>
          </div>
        </div>

        {mobileMenuOpen && (
          <div className="sm:hidden border-t border-line bg-paper pb-3 pt-2">
            <div className="space-y-1">
              <NavLink
                to="/tickets"
                end
                className={mobileNavLinkClass}
                onClick={() => setMobileMenuOpen(false)}
              >
                Tickets
              </NavLink>
              <NavLink
                to="/tickets/new"
                className={mobileNavLinkClass}
                onClick={() => setMobileMenuOpen(false)}
              >
                New ticket
              </NavLink>
              {isStaff && (
                <NavLink
                  to="/reports"
                  className={mobileNavLinkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Reports
                </NavLink>
              )}
              {isStaff && (
                <NavLink
                  to="/ai-quality"
                  className={mobileNavLinkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  AI quality
                </NavLink>
              )}
              {isAdmin && (
                <NavLink
                  to="/holidays"
                  className={mobileNavLinkClass}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Holidays
                </NavLink>
              )}
            </div>
            <div className="pt-4 pb-2 border-t border-line px-4 flex justify-between items-center">
              <div>
                <div className="text-sm font-medium text-ink">{user?.full_name || user?.email}</div>
                <div className="text-xs text-muted uppercase">{role}</div>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="text-sm font-medium text-coral hover:underline"
              >
                Sign out
              </button>
            </div>
          </div>
        )}
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
};
