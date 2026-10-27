import { getAccountId } from "@/lib/auth";

const SESSION_KEY_PREFIX = "visualSearchState:";

export type PerImageStatus = {
  image_index: number;
  status: "valid" | "rejected_not_tile";
  gatekeeper_score: number | null;
  result_count: number;
  error?: string | null;
  preview?: string | null; // data URL for thumbnail
};

export type SavedSearchState = {
  // Legacy single-image fields (kept for backward compat)
  preview: string | null;
  results: unknown[];
  searched: boolean;
  responseMs: number | null;
  // Multi-image extensions
  previews?: (string | null)[];
  perImageStatus?: PerImageStatus[];
  validImageCount?: number;
  rejectedImageCount?: number;
  isMultiImage?: boolean;
};

export function loadSearchSession(): SavedSearchState | null {
  if (typeof window === "undefined") return null;
  const accountId = getAccountId();
  if (!accountId) return null;
  const raw = sessionStorage.getItem(`${SESSION_KEY_PREFIX}${accountId}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SavedSearchState;
  } catch {
    return null;
  }
}

export function saveSearchSession(state: SavedSearchState): void {
  if (typeof window === "undefined") return;
  const accountId = getAccountId();
  if (!accountId) return;
  sessionStorage.setItem(`${SESSION_KEY_PREFIX}${accountId}`, JSON.stringify(state));
}

export function clearSearchSession(): void {
  if (typeof window === "undefined") return;
  const accountId = getAccountId();
  if (accountId) sessionStorage.removeItem(`${SESSION_KEY_PREFIX}${accountId}`);
  sessionStorage.removeItem("visualSearchState");
}
