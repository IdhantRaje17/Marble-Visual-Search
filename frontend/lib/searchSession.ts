const SESSION_KEY = "visualSearchState";

export type SavedSearchState = {
  preview: string | null;
  results: unknown[];
  searched: boolean;
  responseMs: number | null;
};

export function loadSearchSession(): SavedSearchState | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SavedSearchState;
  } catch {
    return null;
  }
}

export function saveSearchSession(state: SavedSearchState): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(state));
}

export function clearSearchSession(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(SESSION_KEY);
}
