import { create } from "zustand";
import { persist } from "zustand/middleware";

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  userId: string | null;
  displayName: string | null;
  tenantId: string | null;
  permissions: string[];
  setTokens: (access: string, refresh: string) => void;
  setProfile: (profile: {
    userId: string | null;
    displayName: string;
    tenantId: string;
    permissions: string[];
  }) => void;
  logout: () => void;
  hasPermission: (permission: string) => boolean;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      userId: null,
      displayName: null,
      tenantId: null,
      permissions: [],
      setTokens: (access, refresh) =>
        set({ accessToken: access, refreshToken: refresh }),
      setProfile: (profile) =>
        set({
          userId: profile.userId,
          displayName: profile.displayName,
          tenantId: profile.tenantId,
          permissions: profile.permissions,
        }),
      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          userId: null,
          displayName: null,
          tenantId: null,
          permissions: [],
        }),
      hasPermission: (permission) => get().permissions.includes(permission),
    }),
    { name: "ai-platform-auth" },
  ),
);
