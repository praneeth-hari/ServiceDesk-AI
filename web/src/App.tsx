import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { RoleRoute } from './components/RoleRoute';
import { AppShell } from './components/AppShell';
import { LoginPage } from './pages/LoginPage';
import { TicketsPage } from './features/tickets/TicketsPage';
import {
  TicketDetailPage,
  NewTicketPage,
  ReportsPage,
  HolidaysPage,
} from './pages/PlaceholderPage';

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/tickets" element={<TicketsPage />} />
              <Route path="/tickets/new" element={<NewTicketPage />} />
              <Route path="/tickets/:id" element={<TicketDetailPage />} />

              <Route element={<RoleRoute staffOnly />}>
                <Route path="/reports" element={<ReportsPage />} />
              </Route>

              <Route element={<RoleRoute adminOnly />}>
                <Route path="/holidays" element={<HolidaysPage />} />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/tickets" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
