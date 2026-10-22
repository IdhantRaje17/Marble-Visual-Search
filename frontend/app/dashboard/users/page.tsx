"use client";

import { useEffect, useState } from "react";
import { Loader2, ShieldCheck, UserRound, Users } from "lucide-react";
import api from "@/lib/api";
import { isAccountRole, type AccountRole } from "@/lib/auth";

type ManagedUser = {
  id: number;
  name: string;
  email: string;
  role: AccountRole;
  is_active: boolean;
};

const roleLabels: Record<AccountRole, string> = {
  super_admin: "Super Admin",
  admin: "Admin",
  user: "User",
};

export default function UserManagementPage() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingUserId, setPendingUserId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const loadUsers = async () => {
    const [usersResponse, currentUserResponse] = await Promise.all([
      api.get<ManagedUser[]>("/api/admin/users"),
      api.get("/api/auth/me"),
    ]);
    setUsers(usersResponse.data);
    setCurrentUserId(currentUserResponse.data.id);
  };

  useEffect(() => {
    loadUsers()
      .catch(() => setError("User accounts could not be loaded."))
      .finally(() => setLoading(false));
  }, []);

  const changeRole = async (user: ManagedUser, role: AccountRole) => {
    setPendingUserId(user.id);
    setError("");
    try {
      await api.patch(`/api/admin/users/${user.id}/role`, { role });
      await loadUsers();
    } catch (err: unknown) {
      const responseError = err as { response?: { data?: { detail?: string } } };
      setError(responseError.response?.data?.detail || "The user's role could not be changed.");
    } finally {
      setPendingUserId(null);
    }
  };

  const changeStatus = async (user: ManagedUser) => {
    setPendingUserId(user.id);
    setError("");
    try {
      await api.patch(`/api/admin/users/${user.id}/status`, {
        is_active: !user.is_active,
      });
      await loadUsers();
    } catch (err: unknown) {
      const responseError = err as { response?: { data?: { detail?: string } } };
      setError(responseError.response?.data?.detail || "The account status could not be changed.");
    } finally {
      setPendingUserId(null);
    }
  };

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex items-center gap-3">
        <Users className="text-cyan-700" aria-hidden="true" />
        <div>
          <h1 className="text-2xl font-bold text-stone-800">User Management</h1>
          <p className="text-sm text-stone-500">Manage account roles and access status</p>
        </div>
      </div>

      {error && (
        <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-stone-500">
            <Loader2 className="animate-spin" aria-hidden="true" /> Loading accounts...
          </div>
        ) : users.length === 0 ? (
          <p className="py-16 text-center text-stone-500">No user accounts found.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Account</th>
                <th className="px-5 py-3 font-semibold">Role</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 font-semibold">Access</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {users.map((user) => {
                const isSelf = user.id === currentUserId;
                const isPending = user.id === pendingUserId;
                return (
                  <tr key={user.id} className="align-middle">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        {user.role === "super_admin" ? (
                          <ShieldCheck size={18} className="text-cyan-700" aria-hidden="true" />
                        ) : (
                          <UserRound size={18} className="text-stone-400" aria-hidden="true" />
                        )}
                        <div>
                          <p className="font-medium text-stone-800">
                            {user.name}{isSelf ? " (you)" : ""}
                          </p>
                          <p className="text-xs text-stone-500">{user.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <label className="sr-only" htmlFor={`role-${user.id}`}>Role for {user.email}</label>
                      <select
                        id={`role-${user.id}`}
                        value={user.role}
                        disabled={isSelf || isPending}
                        onChange={(event) => {
                          const role = event.target.value;
                          if (isAccountRole(role)) void changeRole(user, role);
                        }}
                        className="rounded-md border border-stone-300 bg-white px-3 py-2 text-stone-700 disabled:bg-stone-100 disabled:text-stone-400"
                      >
                        {(["user", "admin", "super_admin"] as AccountRole[]).map((role) => (
                          <option key={role} value={role}>{roleLabels[role]}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-5 py-4">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                        user.is_active ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-600"
                      }`}>
                        {user.is_active ? "Active" : "Suspended"}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        disabled={isSelf || isPending}
                        onClick={() => changeStatus(user)}
                        className="rounded-md border border-stone-300 px-3 py-2 font-medium text-stone-700 transition hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isPending ? "Saving..." : user.is_active ? "Suspend" : "Reactivate"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
