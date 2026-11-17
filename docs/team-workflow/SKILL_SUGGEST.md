---
name: feedback-autoreport-preflight
description: Preflight gate for the scheduled AionUI customer-feedback auto-report task (Drive/Sheets/Docs/Gmail). Verifies Google Workspace tooling exists before any processing.
---

# Feedback Auto-Report Preflight

## Purpose
Runs as the Leader of the scheduled `TestAutoReview` task (every 15 min) that polls a Google Drive folder
(`1u2gQEMVGDi8frZPQlH2Wf8nQ6Xhda5js`) for new customer-feedback Sheets, and (when tools exist) produces an
analysis, a Google Doc report, a Gmail DRAFT (never send), and an updated `Processed Log` sheet.

## Step 0 — Preflight (mandatory, first action every run)
1. Enumerate available tools/skills. Required capabilities:
   - list/search Drive files in the folder
   - read Sheets (read-only on source)
   - write Sheets (log sheet only: `Processed Log`)
   - create Google Docs
   - create Gmail drafts (NOT send)
2. Detect these via: `ToolSearch` (deferred tool registry) for "gmail", "drive", "sheets", "docs", "google";
   check `Get-Command gcloud, gdrive, rclone, gam, sheets`; inspect available skills; check for MCP servers.
3. If ANY capability is missing → **STOP immediately**. Do NOT create the log, do NOT write anything, do NOT
   attempt network/CLI workarounds (hard safety rule). Report in Thai (RESPONSE_LANGUAGE) exactly which
   capability is missing.

## Outcome observed (2026-10-14 execution)
- Environment: Windows PowerShell, no Google Workspace MCP servers, no Google CLI tools, no skills for
  Drive/Sheets/Docs/Gmail. All five required capabilities were MISSING → task halted at Step 0.
- Report format used (Thai, one line per missing capability, then stop line):
  - "ความสามารถที่ขาดหาย: list/search Google Drive, read Google Sheets, write Sheets (log), create Google Docs, create Gmail drafts — ไม่มีอยู่ในสภาพแวดล้อมนี้"
  - "หยุดดำเนินการตาม Step 0 (Preflight) — ไม่สร้างไฟล์ใด ๆ"
- Also honour DRY_RUN=True when set (Steps 0-2 only, create nothing, report what WOULD be done).

## Expected success path (when tools exist) — for future runs
1. Preflight (above) passes.
2. List Sheets in folder; ensure `Processed Log` exists (create only if log missing and not DRY_RUN), with header:
   `Sheet ID | Sheet Name | Detected At | Processed At | Report Doc URL | Gmail Draft ID | Status | Attempts | Notes`
3. Exclude log itself; exclude sheets modified within last 5 min (STABILITY_MINUTES). Housekeeping: IN_PROGRESS
   rows older than 30 min → FAILED (Notes `stale`, Attempts+1). Skip DONE/DONE_WITH_WARNINGS/SKIPPED_EMPTY/
   NEEDS_ATTENTION; retry FAILED only if Attempts < 2, else NEEDS_ATTENTION.
4. Process max 3 sheets (oldest first). Lock each with an IN_PROGRESS row before work, update to final status after.
5. Roles: A) Analyst — infer columns, compute exact numbers (rows, date range, avg score, distribution, category
   counts/%, channel counts, urgent count/%, top-3 categories, data-quality issues); B) Writer — Google Doc
   `Feedback Report - <Sheet> - <YYYY-MM-DD HH:mm>` with 7 required sections; C) Communicator — Gmail DRAFT to
   `nattanan.jansomboon@gmail.com`, subject `[Feedback Report] <Sheet> - <date>`, body with 4-5 headline numbers +
   Doc link + Sheet link + "automated draft" note; D) Reviewer — re-read source sheet, recompute key metrics
   independently, verify Doc/draft numbers and links, recipient, and that it is a draft (never sent).

## Quality criteria
- Zero fabricated data: every number must come from the source sheet; state column mapping/assumptions explicitly.
- Never send email; never delete/move/rename/change permissions on any file; never modify a source feedback sheet.
- On tool failure: retry once, then record failure in log (Status FAILED, Notes with reason) and move on.
- Final run summary in Thai: timestamp, sheets found/processed/skipped, per-sheet Doc link, draft status, review
  result, warnings.
- If team delegation (Spawn) is unavailable, perform all four roles sequentially yourself — Reviewer must still
  recompute from the source independently.