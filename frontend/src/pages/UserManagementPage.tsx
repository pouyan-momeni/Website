import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Loader2, Plus, UserX } from 'lucide-react';

export default function UserManagementPage() {
    const queryClient = useQueryClient();
    const [showForm, setShowForm] = useState(false);
    const [newUser, setNewUser] = useState({ ldap_username: '', email: '', role: 'reader' });

    const { data: users, isLoading } = useQuery({
        queryKey: ['users'],
        queryFn: () => api.getUsers(),
    });

    const createMutation = useMutation({
        mutationFn: () => api.createUser(newUser),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            setShowForm(false);
            setNewUser({ ldap_username: '', email: '', role: 'reader' });
        },
    });

    const updateRoleMutation = useMutation({
        mutationFn: ({ userId, role }: { userId: string; role: string }) => api.updateUserRole(userId, role),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
    });

    const deactivateMutation = useMutation({
        mutationFn: (userId: string) => api.deactivateUser(userId),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
    });

    return (
        <div className="animate-fade-in">
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-2xl font-bold">User Management</h1>
                <button
                    onClick={() => setShowForm(!showForm)}
                    className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                    <Plus className="w-4 h-4" />
                    Add User
                </button>
            </div>

            {/* Add user form */}
            {showForm && (
                <div className="bg-card border border-border rounded-xl p-6 mb-6 animate-fade-in">
                    <h3 className="text-lg font-semibold mb-4">Add New User</h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label className="block text-sm font-medium mb-1.5">LDAP Username</label>
                            <input
                                type="text"
                                value={newUser.ldap_username}
                                onChange={(e) => setNewUser(prev => ({ ...prev, ldap_username: e.target.value }))}
                                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:ring-2 focus:ring-primary/50"
                                placeholder="username"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium mb-1.5">Email</label>
                            <input
                                type="email"
                                value={newUser.email}
                                onChange={(e) => setNewUser(prev => ({ ...prev, email: e.target.value }))}
                                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:ring-2 focus:ring-primary/50"
                                placeholder="user@example.com"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium mb-1.5">Role</label>
                            <select
                                value={newUser.role}
                                onChange={(e) => setNewUser(prev => ({ ...prev, role: e.target.value }))}
                                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:ring-2 focus:ring-primary/50"
                            >
                                <option value="reader">Reader</option>
                                <option value="runner">Runner</option>
                                <option value="developer">Developer</option>
                                <option value="admin">Admin</option>
                            </select>
                        </div>
                    </div>
                    {createMutation.isError && (
                        <p className="text-sm text-red-400 mt-3">{(createMutation.error as Error).message}</p>
                    )}
                    <div className="flex gap-2 mt-4">
                        <button
                            onClick={() => createMutation.mutate()}
                            disabled={createMutation.isPending || !newUser.ldap_username}
                            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                        >
                            {createMutation.isPending ? 'Creating...' : 'Create User'}
                        </button>
                        <button
                            onClick={() => setShowForm(false)}
                            className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent"
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* Users table */}
            {isLoading ? (
                <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>
            ) : (
                <div className="bg-card border border-border rounded-xl overflow-hidden">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border text-muted-foreground text-left">
                                <th className="px-4 py-3 font-medium">Username</th>
                                <th className="px-4 py-3 font-medium">Email</th>
                                <th className="px-4 py-3 font-medium">Role</th>
                                <th className="px-4 py-3 font-medium">Status</th>
                                <th className="px-4 py-3 font-medium">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users?.map(user => (
                                <tr key={user.id} className={`border-b border-border/50 hover:bg-accent/30 transition-colors ${!user.is_active ? 'opacity-50' : ''}`}>
                                    <td className="px-4 py-3 font-medium">{user.ldap_username}</td>
                                    <td className="px-4 py-3 text-muted-foreground">{user.email || '—'}</td>
                                    <td className="px-4 py-3">
                                        <select
                                            value={user.role}
                                            onChange={(e) => updateRoleMutation.mutate({ userId: user.id, role: e.target.value })}
                                            disabled={!user.is_active}
                                            className="px-2 py-1 bg-background border border-border rounded text-sm focus:ring-primary/50"
                                        >
                                            <option value="reader">Reader</option>
                                            <option value="runner">Runner</option>
                                            <option value="developer">Developer</option>
                                            <option value="admin">Admin</option>
                                        </select>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${user.is_active ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
                                            }`}>
                                            {user.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        {user.is_active && (
                                            <button
                                                onClick={() => deactivateMutation.mutate(user.id)}
                                                className="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                                title="Deactivate"
                                            >
                                                <UserX className="w-4 h-4" />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
