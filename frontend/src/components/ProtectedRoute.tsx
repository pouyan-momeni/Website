import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../stores/auth';

interface Props {
    children: React.ReactNode;
    roles: string[];
    requireDevelop?: boolean;
}

export default function ProtectedRoute({ children, roles, requireDevelop }: Props) {
    const { user, appMode } = useAuthStore();

    if (!user) {
        return <Navigate to="/login" replace />;
    }

    if (!roles.includes(user.role)) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <div className="text-center">
                    <h2 className="text-2xl font-bold text-red-400 mb-2">Access Denied</h2>
                    <p className="text-muted-foreground">You don't have permission to view this page.</p>
                </div>
            </div>
        );
    }

    if (requireDevelop && appMode !== 'develop') {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <div className="text-center">
                    <h2 className="text-2xl font-bold text-amber-400 mb-2">Develop Mode Only</h2>
                    <p className="text-muted-foreground">This feature is only available in develop mode.</p>
                </div>
            </div>
        );
    }

    return <>{children}</>;
}
