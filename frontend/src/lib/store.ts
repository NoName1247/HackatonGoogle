"use client";

import { create } from "zustand";

export type UserRole = "COMMISSION" | "STUDENT" | "DEAN";
export type UploadPhase = "IDLE" | "PREFLIGHT" | "UPLOADING" | "STREAMING" | "COMPLETED" | "ERROR";

export interface StreamProgressEvent {
  job_id: string;
  event: string;
  step: number;
  percent: number;
  title: string;
  timestamp: string;
  payload?: Record<string, any>;
}

interface HorizonAppState {
  activeRole: UserRole;
  setActiveRole: (role: UserRole) => void;

  // Upload & SSE Pipeline State Machine
  uploadPhase: UploadPhase;
  currentJobId: string | null;
  progressPercent: number;
  progressStep: number;
  progressTitle: string;
  progressHistory: StreamProgressEvent[];
  uploadError: string | null;

  // Active Project Passport & Detail
  activeProjectId: string | null;
  activeProjectDetail: any | null;
  activeSynergyGraph: any | null;

  // Marketplace Filters (Mode 2)
  filterProfile: string;
  filterModality: string;
  filterHasDataset: boolean;
  filterPureDonorOnly: boolean;
  filterSearchQuery: string;

  // Dean Selection (Mode 3)
  selectedTopicIds: string[];

  // Actions
  setUploadState: (partial: Partial<HorizonAppState>) => void;
  appendProgressEvent: (ev: StreamProgressEvent) => void;
  resetUploadState: () => void;
  setActiveProjectDetail: (detail: any | null) => void;
  setActiveSynergyGraph: (graph: any | null) => void;
  setFilter: (key: string, value: any) => void;
  toggleTopicSelection: (id: string) => void;
  setSelectedTopicIds: (ids: string[]) => void;
}

export const useHorizonStore = create<HorizonAppState>((set) => ({
  activeRole: "COMMISSION",
  setActiveRole: (role) => set({ activeRole: role }),

  uploadPhase: "IDLE",
  currentJobId: null,
  progressPercent: 0,
  progressStep: 0,
  progressTitle: "",
  progressHistory: [],
  uploadError: null,

  activeProjectId: null,
  activeProjectDetail: null,
  activeSynergyGraph: null,

  filterProfile: "all",
  filterModality: "all",
  filterHasDataset: false,
  filterPureDonorOnly: false,
  filterSearchQuery: "",

  selectedTopicIds: [],

  setUploadState: (partial) => set((state) => ({ ...state, ...partial })),
  appendProgressEvent: (ev) =>
    set((state) => {
      const exists = state.progressHistory.some(
        (x) => x.step === ev.step && x.title === ev.title
      );
      return {
        progressPercent: ev.percent ?? state.progressPercent,
        progressStep: ev.step ?? state.progressStep,
        progressTitle: ev.title ?? state.progressTitle,
        progressHistory: exists ? state.progressHistory : [...state.progressHistory, ev],
      };
    }),
  resetUploadState: () =>
    set({
      uploadPhase: "IDLE",
      currentJobId: null,
      progressPercent: 0,
      progressStep: 0,
      progressTitle: "",
      progressHistory: [],
      uploadError: null,
    }),
  setActiveProjectDetail: (detail) =>
    set({
      activeProjectDetail: detail,
      activeProjectId: detail?.project_id ?? null,
    }),
  setActiveSynergyGraph: (graph) => set({ activeSynergyGraph: graph }),
  setFilter: (key, value) => set((state) => ({ ...state, [key]: value })),
  toggleTopicSelection: (id) =>
    set((state) => ({
      selectedTopicIds: state.selectedTopicIds.includes(id)
        ? state.selectedTopicIds.filter((x) => x !== id)
        : [...state.selectedTopicIds, id],
    })),
  setSelectedTopicIds: (ids) => set({ selectedTopicIds: ids }),
}));

