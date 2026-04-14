import { create } from "zustand";

interface SidebarState {
  isCollapsed: boolean;
  toggle: () => void;
  collapse: () => void;
  expand: () => void;
}

export const useSidebarStore = create<SidebarState>((set) => ({
  isCollapsed: false,
  toggle: () => set((state) => ({ isCollapsed: !state.isCollapsed })),
  collapse: () => set({ isCollapsed: true }),
  expand: () => set({ isCollapsed: false }),
}));
