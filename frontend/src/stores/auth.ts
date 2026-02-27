import { create } from 'zustand';
import type { User } from '../types';

interface AuthState {
    accessToken: string | null;
    user: User | null;
    appMode: 'develop' | 'production' | null;
    setAuth: (token: string, user: User) => void;
    setAppMode: (mode: 'develop' | 'production') => void;
    clearAuth: () => void;
    hasRole: (roles: string[]) => boolean;
    isDevelop: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
    accessToken: null,
    user: null,
    appMode: null,

    setAuth: (token, user) => set({ accessToken: token, user }),
    setAppMode: (mode) => set({ appMode: mode }),
    clearAuth: () => set({ accessToken: null, user: null }),

    hasRole: (roles) => {
        const { user } = get();
        return user ? roles.includes(user.role) : false;
    },

    isDevelop: () => {
        const { appMode } = get();
        return appMode === 'develop';
    },
}));
