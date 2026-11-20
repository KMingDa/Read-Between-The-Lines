import { Navigate, Route, Routes } from 'react-router'
import { AuthProvider } from './auth/AuthProvider'
import { Layout } from './components/Layout'
import { RequireAuth } from './components/RequireAuth'
import { AnalyzePage } from './pages/AnalyzePage'
import { ConversationPage } from './pages/ConversationPage'
import { ConversationsPage } from './pages/ConversationsPage'
import { ImportPage } from './pages/ImportPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import './App.css'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/conversations" replace />} />
            <Route path="/conversations" element={<ConversationsPage />} />
            <Route path="/conversations/import" element={<ImportPage />} />
            <Route path="/conversations/:conversationId" element={<ConversationPage />} />
            <Route path="/analyze" element={<AnalyzePage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
