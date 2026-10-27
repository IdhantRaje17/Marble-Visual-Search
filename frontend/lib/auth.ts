export type AccountRole = "super_admin" | "admin" | "user";

export const isAccountRole = (role: unknown): role is AccountRole =>
  role === "super_admin" || role === "admin" || role === "user";

const SEARCH_STATE_PREFIX = "visualSearchState:";

const clearSearchStates = () => {
  if (typeof window === "undefined") return;
  for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = sessionStorage.key(index);
    if (key === "visualSearchState" || key?.startsWith(SEARCH_STATE_PREFIX)) {
      sessionStorage.removeItem(key);
    }
  }
};

export const setSession = (token: string, role: AccountRole, accountId: number) => {
  const previousAccountId = sessionStorage.getItem("accountId");
  if (previousAccountId !== null && previousAccountId !== String(accountId)) {
    clearSearchStates();
  }
  localStorage.removeItem("token");
  localStorage.removeItem("role");
  sessionStorage.setItem("token", token);
  sessionStorage.setItem("role", role);
  sessionStorage.setItem("accountId", String(accountId));
};

export const setToken = (token: string) =>
  sessionStorage.setItem("token", token);

export const setRole = (role: AccountRole) =>
  sessionStorage.setItem("role", role);

export const getToken = () =>
  typeof window !== "undefined" ? sessionStorage.getItem("token") : null;

export const getAccountId = () =>
  typeof window !== "undefined" ? sessionStorage.getItem("accountId") : null;

export const setAccountId = (accountId: number) => {
  const previousAccountId = sessionStorage.getItem("accountId");
  if (previousAccountId !== null && previousAccountId !== String(accountId)) {
    clearSearchStates();
  }
  sessionStorage.setItem("accountId", String(accountId));
};

export const getRole = (): AccountRole | null => {
  if (typeof window === "undefined") return null;
  const role = sessionStorage.getItem("role");
  return isAccountRole(role) ? role : null;
};

export const removeToken = () => {
  clearSearchStates();
  sessionStorage.removeItem("token");
  sessionStorage.removeItem("role");
  sessionStorage.removeItem("accountId");
  localStorage.removeItem("token");
  localStorage.removeItem("role");
};

export const isLoggedIn = () => !!getToken();