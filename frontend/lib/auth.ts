export type AccountRole = "super_admin" | "admin" | "user";

export const isAccountRole = (role: unknown): role is AccountRole =>
  role === "super_admin" || role === "admin" || role === "user";

export const setToken = (token: string) =>
  localStorage.setItem("token", token);

export const setRole = (role: AccountRole) =>
  localStorage.setItem("role", role);

export const getToken = () =>
  typeof window !== "undefined" ? localStorage.getItem("token") : null;

export const getRole = (): AccountRole | null => {
  if (typeof window === "undefined") return null;
  const role = localStorage.getItem("role");
  return isAccountRole(role) ? role : null;
};

export const removeToken = () => {
  localStorage.removeItem("token");
  localStorage.removeItem("role");
};

export const isLoggedIn = () => !!getToken();