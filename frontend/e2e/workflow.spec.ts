import { test, expect } from "@playwright/test";
import path from "node:path";

test("demo, evidence, manual review, report and optional status", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Run demo reconciliation" }).click();
  await expect(
    page.getByText(
      "Reconciliation complete. Evidence and source snapshots have been saved.",
    ),
  ).toBeVisible();
  await expect(page.getByText("180", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Reconciliation", exact: true })
    .click();
  await page.getByLabel("Search records").fill("L004");
  await page.getByRole("button", { name: "L004", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page
      .getByRole("dialog")
      .getByText("Unexplained amount difference;", { exact: false })
      .first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Investigate evidence" }).click();
  await expect(page.getByText("rule-based · AI_DISABLED")).toBeVisible();
  await page
    .getByLabel("Reason or note (required)")
    .fill("Browser test: amount needs source verification");
  await page.getByRole("button", { name: "Leave unresolved" }).click();
  await expect(
    page.getByText(
      "Decision saved with actor, reason and previous status in the audit trail.",
    ),
  ).toBeVisible();
  await expect(
    page.getByText("Browser test: amount needs source verification", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByLabel("Close details").click();
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Audit Download CSV report" }).click();
  expect((await downloaded).suggestedFilename()).toBe("audit.csv");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByText("No", { exact: true })).toHaveCount(3);
  await expect(
    page.getByRole("button", { name: "Fetch live records" }),
  ).toBeDisabled();
  await page.screenshot({
    path: "../runtime/dashboard-settings.png",
    fullPage: true,
  });
});

test("four file import, preview and reconciliation", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Import data", exact: true }).click();
  for (const source of [
    "internal_ledger",
    "razorpay_recon",
    "razorpay_settlements",
    "bank_statement",
  ]) {
    const upload = page.getByLabel("Upload " + source, { exact: true });
    await upload.setInputFiles(path.resolve("../data/" + source + ".csv"));
    const card = page.locator("section.import-card").filter({ has: upload });
    await card.getByRole("button", { name: "Validate and preview" }).click();
    await expect(card.getByText("Preview accepted records")).toBeVisible();
  }
  await expect(page.getByText("4 of 4 sources validated")).toBeVisible();
  await page
    .getByRole("button", { name: "Reconcile uploaded dataset" })
    .click();
  await expect(page.locator(".source-banner strong")).toHaveText("Uploaded");
  await expect(
    page.getByRole("heading", { name: "Reconciliation overview" }),
  ).toBeVisible();
  await expect(page.locator(".sidebar")).toBeVisible();
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await page.screenshot({ path: "../runtime/dashboard.png", fullPage: true });
});

test("responsive layout and navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Toggle menu").click();
  await page
    .getByRole("button", { name: "Review queue", exact: false })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Review queue", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
