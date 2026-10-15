import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { useAuth } from './context/AuthContext'
import { BenchmarkDetailPage } from './pages/BenchmarkDetailPage'
import { BenchmarksPage } from './pages/BenchmarksPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { RegisterPage } from './pages/RegisterPage'
import { SessionsPage } from './pages/SessionsPage'

export function App() {
  const { status } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={status === 'authenticated' ? <Navigate to="/documents" replace /> : <LoginPage />} />
      <Route
        path="/register"
        element={status === 'authenticated' ? <Navigate to="/documents" replace /> : <RegisterPage />}
      />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/benchmarks" element={<BenchmarksPage />} />
          <Route path="/benchmarks/:jobId" element={<BenchmarkDetailPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/documents" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
