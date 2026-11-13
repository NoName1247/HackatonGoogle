"use client";

import { fetchEventSource } from "@microsoft/fetch-event-source";
import { StreamProgressEvent, useHorizonStore } from "./store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

/**
 * Browser Preflight Guard (Section 4.4 of Spec):
 * 1. Verifies file size <= 25 MB.
 * 2. Reads first 8 bytes via FileReader to verify `%PDF-1.` or `%PDF-2.` signature before network upload.
 */
export async function validatePdfFilePreflight(file: File): Promise<{ valid: boolean; error?: string }> {
  if (!file) {
    return { valid: false, error: "No file selected." };
  }
  if (file.size > 25 * 1024 * 1024) {
    return { valid: false, error: "File exceeds the 25 MB limit." };
  }
  if (file.size < 64) {
    return { valid: false, error: "File is too small (< 64 bytes) to be a valid PDF." };
  }

  try {
    const slice = file.slice(0, 8);
    const buffer = await slice.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const header = String.fromCharCode(...Array.from(bytes));
    if (!header.startsWith("%PDF-1.") && !header.startsWith("%PDF-2.")) {
      return {
        valid: false,
        error: `Invalid PDF signature ("${header.slice(0, 7)}"). Expected "%PDF-1.x".`,
      };
    }
    return { valid: true };
  } catch (err: any) {
    return { valid: false, error: err?.message || "Failed to read file header." };
  }
}

/**
 * Generates a realistic 2-page PDF in memory (`%PDF-1.4`) so judges can test the live 6-step
 * ingestion pipeline in 1 click without needing a local PDF file on their machine.
 */
export function buildSampleDemoPdfFile(): File {
  const pdfContent = `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 780 >>
stream
BT
/F1 11 Tf
50 740 Td
(Department of Computer Vision & Nondestructive Testing) Tj
0 -20 Td
(Title: Automated Defect Segmentation in X-Ray Radiographs of Welded Joints) Tj
0 -20 Td
(Author: Elias Vance | Supervisor: Prof. Arthur Pendelton | Year: 2025) Tj
0 -30 Td
(# Chapter 2. Methodology and Dataset) Tj
0 -18 Td
(We curated a primary dataset of N = 1800 digital weld radiographs in COCO format.) Tj
0 -30 Td
(# Chapter 3. Experimental Evaluation) Tj
0 -18 Td
(Initially we tried YOLOv8-seg, which failed on micro-cracks with F1 = 0.31.) Tj
0 -18 Td
(| Class | Samples | F1 | CPU Latency |) Tj
0 -16 Td
(| Low-Contrast Speckle | 330 | 0.52 | 3.2 sec/frame |) Tj
0 -18 Td
(Note: Video stream ingestion is implemented as a local folder file-reading stub without batching.) Tj
0 -30 Td
(# Conclusion and Future Work) Tj
0 -18 Td
(Developed a real-time recognition system with 94% accuracy. Future work: build an iOS app and integrate a speckle-noise filter and ONNX INT8 quantization <30ms.) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000229 00000 n 
0000000297 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
1129
%%EOF`;
  const blob = new Blob([pdfContent], { type: "application/pdf" });
  return new File([blob], "Live_Thesis_Weld_XRay_Audit.pdf", { type: "application/pdf" });
}

export async function uploadThesisAndSubscribeSSE(
  file: File,
  repoUrl?: string,
  explicitTitle?: string
): Promise<void> {
  const store = useHorizonStore.getState();
  store.resetUploadState();
  store.setUploadState({ uploadPhase: "PREFLIGHT", progressTitle: "Running Preflight PDF Guard (%PDF-1.x & size check)..." });

  const check = await validatePdfFilePreflight(file);
  if (!check.valid) {
    store.setUploadState({ uploadPhase: "ERROR", uploadError: check.error || "Preflight validation failed." });
    return;
  }

  store.setUploadState({ uploadPhase: "UPLOADING", progressPercent: 5, progressTitle: "Streaming PDF to Horizon Relay API..." });

  const formData = new FormData();
  formData.append("file", file);
  if (repoUrl && repoUrl.trim()) formData.append("repo_url", repoUrl.trim());
  if (explicitTitle && explicitTitle.trim()) formData.append("title", explicitTitle.trim());

  let ingestResp: any;
  try {
    const res = await fetch(`${API_BASE}/projects/ingest`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `Upload failed with HTTP ${res.status}`);
    }
    ingestResp = await res.json();
  } catch (err: any) {
    store.setUploadState({ uploadPhase: "ERROR", uploadError: err?.message || "Network upload error." });
    return;
  }

  const jobId = ingestResp.job_id;
  const projectId = ingestResp.project_id;
  store.setUploadState({
    uploadPhase: "STREAMING",
    currentJobId: jobId,
    progressPercent: 10,
    progressTitle: "Subscribed to Redis Stream SSE (Waiting for Worker Pool)...",
  });

  let completed = false;
  const abortCtrl = new AbortController();

  // Short-Polling Fallback function if corporate firewall cuts SSE stream
  const startPollingFallback = async () => {
    for (let attempt = 0; attempt < 45; attempt++) {
      if (completed) return;
      try {
        const pollRes = await fetch(`${API_BASE}/jobs/${jobId}/stream?fallback=poll`);
        if (pollRes.ok) {
          const pollData = await pollRes.json();
          const events: StreamProgressEvent[] = pollData.events || [];
          for (const ev of events) {
            useHorizonStore.getState().appendProgressEvent(ev);
            if (ev.event === "completed") {
              completed = true;
              const targetPid = ev.payload?.project_id || projectId;
              await fetchAndSetProjectDetail(targetPid);
              useHorizonStore.getState().setUploadState({ uploadPhase: "COMPLETED", progressPercent: 100 });
              return;
            }
            if (ev.event === "error") {
              completed = true;
              useHorizonStore.getState().setUploadState({
                uploadPhase: "ERROR",
                uploadError: ev.title || "Pipeline failed.",
              });
              return;
            }
          }
        }
      } catch {
        // Ignore transient poll error
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  };

  try {
    await fetchEventSource(`${API_BASE}/jobs/${jobId}/stream`, {
      method: "GET",
      signal: abortCtrl.signal,
      openWhenHidden: true,
      onmessage(msg) {
        if (!msg.data || msg.event === "ping") return;
        try {
          const parsed: StreamProgressEvent = JSON.parse(msg.data);
          useHorizonStore.getState().appendProgressEvent(parsed);

          if (msg.event === "completed" || parsed.event === "completed") {
            completed = true;
            abortCtrl.abort();
            const finalPid = parsed.payload?.project_id || projectId;
            fetchAndSetProjectDetail(finalPid).then(() => {
              useHorizonStore.getState().setUploadState({
                uploadPhase: "COMPLETED",
                progressPercent: 100,
              });
            });
          } else if (msg.event === "error" || parsed.event === "error") {
            completed = true;
            abortCtrl.abort();
            useHorizonStore.getState().setUploadState({
              uploadPhase: "ERROR",
              uploadError: parsed.title || "Worker error.",
            });
          }
        } catch {
          // Ignore malformed event
        }
      },
      onerror(err) {
        abortCtrl.abort();
        throw err;
      },
    });
  } catch {
    if (!completed) {
      await startPollingFallback();
    }
  }
}

export async function fetchProjectsCatalog(params?: Record<string, any>): Promise<any[]> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "" && v !== "all" && v !== false) {
        qs.set(k, String(v));
      }
    });
  }
  const res = await fetch(`${API_BASE}/projects?${qs.toString()}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.items || [];
}

export async function fetchAndSetProjectDetail(projectId: string): Promise<any | null> {
  try {
    const res = await fetch(`${API_BASE}/projects/${projectId}`);
    if (!res.ok) return null;
    const detail = await res.json();
    useHorizonStore.getState().setActiveProjectDetail(detail);
    return detail;
  } catch {
    return null;
  }
}

export async function fetchProjectSynergy(projectId: string, bountyQuery?: string): Promise<any | null> {
  try {
    const qs = bountyQuery ? `?bounty_query=${encodeURIComponent(bountyQuery)}` : "";
    const res = await fetch(`${API_BASE}/projects/${projectId}/synergy${qs}`);
    if (!res.ok) return null;
    const data = await res.json();
    useHorizonStore.getState().setActiveSynergyGraph(data);
    return data;
  } catch {
    return null;
  }
}

export async function generateHandoverPackageApi(
  projectId: string,
  payload?: { donor_project_id?: string; donor_supply_item_id?: string; follower_student_name?: string }
): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/package`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) throw new Error("Failed to generate handover package.");
  return res.json();
}

export async function claimProjectBatonApi(
  projectId: string,
  payload: {
    demand_item_id: string;
    donor_supply_item_id?: string;
    follower_student_name: string;
    approving_supervisor_name: string;
    new_project_title?: string;
    accept_citation_contract: boolean;
  }
): Promise<any> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Claim failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchDeanAnalyticsApi(year?: number, department?: string): Promise<any | null> {
  const qs = new URLSearchParams();
  if (year) qs.set("year", String(year));
  if (department && department !== "all") qs.set("department", department);
  const res = await fetch(`${API_BASE}/analytics/bottlenecks?${qs.toString()}`);
  if (!res.ok) return null;
  return res.json();
}

export async function executeDeanActionApi(payload: {
  action_type: "export_vkr_bank" | "export_grant_justification" | "approve_domain" | "trigger_reclustering";
  project_ids?: string[];
  cluster_id?: string;
  domain_id?: string;
  academic_year_target?: string;
  reviewer_name?: string;
}): Promise<any> {
  const res = await fetch(`${API_BASE}/analytics/export-topics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to execute Dean's action.");
  return res.json();
}

