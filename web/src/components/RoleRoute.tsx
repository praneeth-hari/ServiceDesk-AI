import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import { UserRole } from '../api/types';

export interface RoleRouteProps {
  allowedRoles?: UserRole[];
  staffOnly?: boolean;
  adminOnly?: boolean;
  fallbackPath?: string;
  children?: React.ReactNode;
}

export const RoleRoute: React.FC<RoleRouteProps> = ({
  allowedRoles,
  staffOnly = false,
  adminOnly = false,
  fallbackPath = '/tickets',
  children,
}) => {
  const { user, role, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="text-muted text-sm font-sans animate-pulse">Loading...</div>
      </div>
    );
  }

  if (!user || !role) {
    return <Navigate to="/login" replace />;
  }

  let authorized = true;

  if (adminOnly) {
    authorized = role === 'admin';
  } else if (staffOnly) {
    authorized = role === 'agent' || role === 'admin';
  } else if (allowedRoles && allowedRoles.length > 0) {
    authorized = allowedRoles.includes(role);
  }

  if (!authorized) {
    return <Navigate to={fallbackPath} replace />;
  }

  return children ? <>{children}</> : <Outlet />;
};
