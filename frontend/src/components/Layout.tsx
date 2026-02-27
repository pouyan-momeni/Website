import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../stores/auth';
import { api } from '../api/client';
import {
    BarChart3, Clock, History, Cpu, Users, Settings, Code, LogOut,
    Play, Activity, FileText,
} from 'lucide-react';

const NAV_ITEMS = [
    { path: '/run', label: 'Run Model', icon: Play, roles: ['admin', 'developer', 'runner'] },
    { path: '/settings', label: 'Model Settings', icon: Settings, roles: ['admin'], requireDevelop: true },
    { path: '/history', label: 'Run History', icon: History, roles: ['admin', 'developer', 'runner', 'reader'] },
    { path: '/queue', label: 'Run Queue', icon: Clock, roles: ['admin', 'developer', 'runner'] },
    { path: '/monitoring', label: 'Monitoring', icon: Cpu, roles: ['admin', 'developer', 'runner'] },
    { path: '/admin/users', label: 'Users', icon: Users, roles: ['admin'] },
    { path: '/notebooks', label: 'Notebooks', icon: Code, roles: ['admin', 'developer'] },
    { path: '/audit', label: 'Audit Log', icon: FileText, roles: ['admin'] },
];

export default function Layout() {
    const { user, clearAuth, appMode } = useAuthStore();
    const navigate = useNavigate();
    const location = useLocation();

    const handleLogout = async () => {
        try {
            await api.logout();
        } catch { }
        clearAuth();
        navigate('/login');
    };

    if (!user) {
        navigate('/login');
        return null;
    }

    const filteredNav = NAV_ITEMS.filter(item => {
        if (!item.roles.includes(user.role)) return false;
        if (item.requireDevelop && appMode !== 'develop') return false;
        return true;
    });

    return (
        <div className="flex h-screen bg-background">
            {/* Sidebar */}
            <aside className="w-64 border-r border-border bg-card flex flex-col">
                {/* Logo */}
                <div className="p-4 border-b border-border">
                    <div className="flex items-center gap-2">
                        <Activity className="w-6 h-6 text-primary" />
                        <span className="text-lg font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                            ALM Platform
                        </span>
                    </div>
                    {appMode === 'develop' && (
                        <span className="mt-1 inline-block text-[10px] uppercase tracking-wider text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded">
                            develop
                        </span>
                    )}
                </div>

                {/* Navigation */}
                <nav className="flex-1 p-3 space-y-1">
                    {filteredNav.map(item => {
                        const Icon = item.icon;
                        const active = location.pathname === item.path;
                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${active
                                    ? 'bg-primary/10 text-primary font-medium'
                                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                                    }`}
                            >
                                <Icon className="w-4 h-4" />
                                {item.label}
                            </Link>
                        );
                    })}
                </nav>

                {/* User info */}
                <div className="p-3 border-t border-border">
                    <div className="flex items-center justify-between">
                        <div className="min-w-0">
                            <p className="text-sm font-medium truncate">{user.ldap_username}</p>
                            <p className="text-xs text-muted-foreground capitalize">{user.role}</p>
                        </div>
                        <button
                            onClick={handleLogout}
                            className="p-2 rounded-lg text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                            title="Logout"
                        >
                            <LogOut className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            </aside>

            {/* Main content */}
            <main className="flex-1 overflow-auto">
                <div className="p-6">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
