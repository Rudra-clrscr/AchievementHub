import { Navigate, Route, Routes } from "react-router-dom";
import "./App.css";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { StudentDashboard } from "./pages/StudentDashboard";
import { CoordinatorDashboard } from "./pages/CoordinatorDashboard";
import { PublicFeed } from "./pages/PublicFeed";

function RequireRole({ roles, children }: { roles: string[]; children: React.ReactNode }) {
  const { session } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  if (!roles.includes(session.role)) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<PublicFeed />} />
      <Route path="/landing" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/student"
        element={
          <RequireRole roles={["student"]}>
            <StudentDashboard />
          </RequireRole>
        }
      />
      <Route
        path="/coordinator"
        element={
          <RequireRole roles={["faculty_coordinator", "admin_hod", "admin_clerk"]}>
            <CoordinatorDashboard />
          </RequireRole>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}

export default App;
