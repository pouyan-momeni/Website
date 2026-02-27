import { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './stores/auth';
import { api } from './api/client';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import ModelRunPage from './pages/ModelRunPage';
import RunQueuePage from './pages/RunQueuePage';
import RunHistoryPage from './pages/RunHistoryPage';
import RunDetailPage from './pages/RunDetailPage';
import MonitoringPage from './pages/MonitoringPage';
import UserManagementPage from './pages/UserManagementPage';
import ModelAdminPage from './pages/ModelAdminPage';
import NotebooksPage from './pages/NotebooksPage';
import AuditLogPage from './pages/AuditLogPage';

export default function App() {
    const { setAppMode } = useAuthStore();

    useEffect(() => {
        api.getMode().then(({ mode }) => {
            setAppMode(mode as 'develop' | 'production');
        }).catch(() => { });
    }, [setAppMode]);

    return (
        <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<Layout />}>
                <Route index element={<Navigate to="/run" replace />} />
                <Route path="run" element={
                    <ProtectedRoute roles={['admin', 'developer', 'runner']}>
                        <ModelRunPage />
                    </ProtectedRoute>
                } />
                <Route path="settings" element={
                    <ProtectedRoute roles={['admin']} requireDevelop>
                        <ModelAdminPage />
                    </ProtectedRoute>
                } />
                <Route path="queue" element={
                    <ProtectedRoute roles={['admin', 'developer', 'runner']}>
                        <RunQueuePage />
                    </ProtectedRoute>
                } />
                <Route path="history" element={
                    <ProtectedRoute roles={['admin', 'developer', 'runner', 'reader']}>
                        <RunHistoryPage />
                    </ProtectedRoute>
                } />
                <Route path="runs/:id" element={
                    <ProtectedRoute roles={['admin', 'developer', 'runner', 'reader']}>
                        <RunDetailPage />
                    </ProtectedRoute>
                } />
                <Route path="monitoring" element={
                    <ProtectedRoute roles={['admin', 'developer', 'runner']}>
                        <MonitoringPage />
                    </ProtectedRoute>
                } />
                <Route path="admin/users" element={
                    <ProtectedRoute roles={['admin']}>
                        <UserManagementPage />
                    </ProtectedRoute>
                } />
                <Route path="notebooks" element={
                    <ProtectedRoute roles={['admin', 'developer']}>
                        <NotebooksPage />
                    </ProtectedRoute>
                } />
                <Route path="audit" element={
                    <ProtectedRoute roles={['admin']}>
                        <AuditLogPage />
                    </ProtectedRoute>
                } />
            </Route>
        </Routes>
    );
}
