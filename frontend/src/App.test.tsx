import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import App from "./App";
import { api, download } from "./api";
import type { Run, Settings, Case } from "./types";
vi.mock("./api", async () => ({
  ...(await vi.importActual("./api")),
  api: vi.fn(),
  download: vi.fn(),
}));
const selected = {
  id: "ledger_razorpay:row1",
  profile: "ledger_razorpay",
  left: {
    id: "L004",
    row_id: "row1",
    amount: 10000,
    date: "2026-01-01",
    original: {},
  },
  right: {
    id: "pay004",
    row_id: "pay1",
    amount: 11000,
    date: "2026-01-01",
    original: {},
  },
  status: "REVIEW",
  automated_status: "REVIEW",
  effective_status: "REVIEW",
  reason: "Amount discrepancy",
  residual: 0,
  alternatives: [],
  evidence: null,
  recommended_action: "Review the source",
} as Case;
const fixture = {
  id: "run1",
  created: "2026-01-01T00:00:00Z",
  cases: [selected],
  config: {},
  provenance: { mode: "synthetic demo", hashes: {} },
  metrics: {
    ledger_count: 180,
    event_count: 189,
    settlement_count: 32,
    bank_count: 152,
    matched: 0,
    review: 1,
    unmatched: 0,
    outstanding_residual: 0,
    expected_settlement: 10000,
    associated_bank_credits: 11000,
    confirmed_bank_credits: 0,
    unexplained_variance: 1000,
    statuses: { REVIEW: 1 },
  },
  unmatched_bank: [],
  unmatched_events: [],
} as Run;
const setting = {
  gemini: {
    state: "AI_DISABLED",
    model: "Not configured",
    requests_used: 0,
    request_limit: 10,
  },
  razorpay: {
    state: "NOT_CONFIGURED",
    configured: false,
    connected: false,
    connection_tested: false,
    message: "Optional credentials absent",
    webhooks_configured: false,
  },
  sources: [],
  required_columns: {},
  reports: ["matched", "audit"],
  config: { weights: {} },
  calendar: { source: "Local calendar", last_verified: null },
  security: "Local single-user",
} as Settings;
beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/settings" ? setting : path === "/runs" ? [] : fixture,
  );
});
it("shows honest empty state and optional integrations", async () => {
  render(<App />);
  await screen.findByText("Ready for your first reconciliation");
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(
    await screen.findByText("AI DISABLED", { exact: false }),
  ).toBeInTheDocument();
  expect(screen.getByText("Optional credentials absent")).toBeInTheDocument();
});
it("runs actual API flow and filters records", async () => {
  vi.mocked(api).mockImplementation(async (path, options) =>
    path === "/settings"
      ? setting
      : path === "/runs" && options?.method !== "POST"
        ? []
        : fixture,
  );
  render(<App />);
  const start = screen.getByRole("button", { name: "Run demo reconciliation" });
  expect(start).toBeDisabled();
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  await screen.findByText(
    "Reconciliation complete. Evidence and source snapshots have been saved.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Reconciliation" }));
  expect(screen.getByRole("button", { name: "L004" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search records"), {
    target: { value: "not-found" },
  });
  expect(screen.getByText("No matching records")).toBeInTheDocument();
});
it("shows service errors safely", async () => {
  vi.mocked(api).mockRejectedValue(new Error("Service unavailable"));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
});
it("requires a reason for persisted review", async () => {
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/settings"
      ? setting
      : path === "/runs"
        ? [
            {
              id: "run1",
              created: fixture.created,
              provenance: fixture.provenance,
            },
          ]
        : fixture,
  );
  render(<App />);
  await screen.findByRole("button", { name: "L004" });
  fireEvent.click(screen.getByRole("button", { name: "L004" }));
  const confirm = screen.getByRole("button", { name: "Confirm match" });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Reason or note (required)"), {
    target: { value: "Checked supporting evidence" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Reject candidate" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/runs/run1/decisions/ledger_razorpay%3Arow1",
      expect.objectContaining({ method: "POST" }),
    ),
  );
});
it("downloads a report for the selected run", async () => {
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/settings"
      ? setting
      : path === "/runs"
        ? [
            {
              id: "run1",
              created: fixture.created,
              provenance: fixture.provenance,
            },
          ]
        : fixture,
  );
  render(<App />);
  await screen.findByRole("button", { name: "L004" });
  fireEvent.click(screen.getByRole("button", { name: "Reports" }));
  fireEvent.click(
    screen.getByRole("button", { name: /Matched.*Download CSV report/ }),
  );
  await waitFor(() =>
    expect(download).toHaveBeenCalledWith(
      "/runs/run1/reports/matched",
      "matched.csv",
    ),
  );
});
