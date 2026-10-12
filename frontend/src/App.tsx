import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Download,
  FileSpreadsheet,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  Play,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
  Layers,
  CircleAlert,
  History,
  PanelLeftClose,
} from "lucide-react";
import { api, currency, download, label } from "./api";
import type { Case, Explanation, Imported, Run, Settings } from "./types";

const sources = [
  "internal_ledger",
  "razorpay_recon",
  "razorpay_settlements",
  "bank_statement",
];
const relationships: Record<string, string> = {
  ledger_razorpay: "Ledger ↔ Razorpay",
  settlement_bank: "Settlements ↔ bank",
  direct_bank: "Direct ledger ↔ bank",
};
const nav = [
  ["Overview", LayoutDashboard],
  ["Import data", Upload],
  ["Reconciliation", Layers],
  ["Review queue", ListChecks],
  ["Settlements", FileSpreadsheet],
  ["Reports", Download],
  ["Settings", Settings2],
] as const;
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status.toLowerCase()}>{label(status)}</span>
  );
}
function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty">
      <Layers size={30} />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("Overview");
  const [run, setRun] = useState<Run | null>(null);
  const [runs, setRuns] = useState<
    { id: string; created: string; provenance: { mode: string } }[]
  >([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Case | null>(null);
  const [search, setSearch] = useState("");
  const [profile, setProfile] = useState("ledger_razorpay");
  const [status, setStatus] = useState("All statuses");
  const [imports, setImports] = useState<Record<string, Imported>>({});
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  const [actor, setActor] = useState("Local reviewer");
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [token, setToken] = useState(
    sessionStorage.getItem("recon-token") || "",
  );
  const [resource, setResource] = useState("payments");
  const [fromDate, setFromDate] = useState("2026-01-01");
  const [toDate, setToDate] = useState("2026-01-31");
  const [fetchResult, setFetchResult] = useState<{
    id: string;
    count: number;
    message: string;
  } | null>(null);
  const [days, setDays] = useState(2);
  const [holidays, setHolidays] = useState("{}");
  const [menu, setMenu] = useState(false);
  const refresh = async () => {
    const [s, h] = await Promise.all([
      api<Settings>("/settings"),
      api<typeof runs>("/runs"),
    ]);
    setSettings(s);
    setRuns(h);
    return h;
  };
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page]);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const h = await refresh();
        if (h.length) {
          const r = await api<Run>("/runs/" + h[0].id);
          if (active) setRun(r);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        if (active) setBusy(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!selected) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const drawer = document.querySelector<HTMLElement>(".drawer");
    const focusable = () =>
      Array.from(
        drawer?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input,textarea,select,summary,[tabindex='0']",
        ) || [],
      );
    focusable()[0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelected(null);
      if (event.key === "Tab") {
        const elements = focusable();
        const first = elements[0],
          last = elements.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKey);
      previousFocus?.focus();
    };
  }, [selected?.id]);
  async function task(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reconcile(uploaded = false) {
    await task(async () => {
      const r = await api<Run>("/runs", {
        method: "POST",
        body: JSON.stringify({
          import_ids: uploaded
            ? Object.fromEntries(sources.map((s) => [s, imports[s].id]))
            : {},
          acknowledge_rejected: ack,
          config: {
            settlement_working_days: days,
            holidays: JSON.parse(holidays),
          },
        }),
      });
      setRun(r);
      await refresh();
      setPage("Overview");
      setNotice(
        "Reconciliation complete. Evidence and source snapshots have been saved.",
      );
    });
  }
  async function decide(action: string) {
    if (!run || !selected) return;
    await task(async () => {
      await api(
        `/runs/${run.id}/decisions/${encodeURIComponent(selected.id)}`,
        { method: "POST", body: JSON.stringify({ action, actor, note }) },
      );
      const r = await api<Run>("/runs/" + run.id);
      setRun(r);
      setSelected((current) =>
        current?.id === selected.id
          ? r.cases.find((c) => c.id === selected.id) || null
          : current,
      );
      setNote("");
      setNotice(
        "Decision saved with actor, reason and previous status in the audit trail.",
      );
    });
  }
  function open(c: Case) {
    setSelected(c);
    setExplanation(c.investigation || null);
    setNote("");
  }
  const filtered = useMemo(
    () =>
      run?.cases.filter(
        (c) =>
          (page === "Review queue"
            ? c.effective_status !== "MATCHED"
            : page === "Settlements"
              ? c.profile === "settlement_bank"
              : c.profile === profile) &&
          (status === "All statuses" || c.effective_status === status) &&
          JSON.stringify([
            c.left.id,
            c.right?.id,
            c.left.reference,
            c.left.name,
            c.reason,
          ])
            .toLowerCase()
            .includes(search.toLowerCase()),
      ) || [],
    [run, page, profile, status, search],
  );
  const m = run?.metrics;
  const unresolved =
    run?.cases.filter((c) => c.effective_status !== "MATCHED") || [];
  const statusCounts =
    run?.cases.reduce(
      (total, c) => ({
        ...total,
        [c.effective_status]: (total[c.effective_status] || 0) + 1,
      }),
      {} as Record<string, number>,
    ) || {};
  return (
    <div className="app-shell">
      <aside className={menu ? "sidebar visible" : "sidebar"}>
        <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
          <div className="brandmark">
            <Layers size={24} />
          </div>
          <span>
            clearledger<span className="brand-small">RECONCILIATION</span>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <div className="merchant">
          <span className="avatar">DM</span>
          <div>
            <strong>Demo merchant</strong>
            <small>India · INR</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <nav>
          {nav.map(([name, Icon]) => (
            <button
              key={name}
              className={page === name ? "active" : ""}
              onClick={() => {
                setPage(name);
                setMenu(false);
                setSearch("");
                setStatus("All statuses");
              }}
            >
              <Icon size={18} />
              {name}
              {name === "Review queue" && run && (
                <span className="nav-count">{unresolved.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <ShieldCheck size={18} />
          <div>
            <strong>Local workspace</strong>
            <small>Source evidence preserved</small>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label="Toggle menu"
            onClick={() => setMenu(!menu)}
          >
            <PanelLeftClose size={20} />
          </button>
          <div>
            <span className="breadcrumb">Workspace</span>
            <ChevronRight size={13} />
            <strong>{page}</strong>
          </div>
          <span className="local-indicator">
            <i />
            Local single-user mode
          </span>
          <span className="avatar small">VR</span>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">FINANCIAL OPERATIONS</div>
              <h1>{page === "Overview" ? "Reconciliation overview" : page}</h1>
              <p>
                {page === "Overview"
                  ? "Follow the money. Resolve differences with source evidence."
                  : page === "Import data"
                    ? "Validate your source files before making financial decisions."
                    : page === "Review queue"
                      ? "Review uncertainty and record a defensible decision."
                      : page === "Settings"
                        ? "Your financial rules and optional service connections."
                        : "Every result traces back to a source record."}
              </p>
            </div>
            <button
              className="primary"
              disabled={busy}
              onClick={() => reconcile(false)}
            >
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Play size={16} />
              )}
              Run demo reconciliation
            </button>
          </div>
          {error && (
            <div role="alert" className="message error">
              <CircleAlert size={18} />
              {error}
              <button
                className="icon-button"
                onClick={() => setError("")}
                aria-label="Dismiss error"
              >
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="message success">
              <Check size={18} />
              {notice}
            </div>
          )}
          <div className="source-banner">
            <div>
              <span className="source-dot" />
              <strong>
                {run ? label(run.provenance.mode) : "Demo dataset available"}
              </strong>
              <span>
                {run
                  ? "Run " +
                    run.id.slice(0, 8) +
                    " · " +
                    new Date(run.created).toLocaleString("en-IN", {
                      timeZone: "Asia/Kolkata",
                    })
                  : "Synthetic data · No API credentials required"}
              </span>
            </div>
            <button
              className="text-button"
              onClick={() => setPage("Import data")}
            >
              Manage sources
              <ArrowRight size={14} />
            </button>
          </div>
          {page === "Overview" && (
            <>
              {!run ? (
                <Empty
                  title="Ready for your first reconciliation"
                  detail="Run the synthetic dataset to see supported matches, residuals and honest exceptions."
                />
              ) : (
                <>
                  <div className="stats-grid">
                    <Stat
                      title="Automatically matched"
                      value={String(m?.matched)}
                      caption="Automated relationship decisions"
                      color="green"
                    />
                    <Stat
                      title="Requires attention"
                      value={String(unresolved.length)}
                      caption="Current review, partial, failed & unmatched"
                      color="amber"
                    />
                    <Stat
                      title="Outstanding ledger residual"
                      value={currency(m!.outstanding_residual)}
                      caption="Automated allocations; excludes settlements"
                    />
                    <Stat
                      title="Settlement differences"
                      value={currency(m!.unexplained_variance)}
                      caption="Absolute proposed bank-credit differences"
                      color="red"
                    />
                  </div>
                  <div className="overview-grid">
                    <section className="panel">
                      <PanelTitle
                        title="Reconciliation by relationship"
                        subtitle="Separate evidence models for each financial stage"
                      />
                      <div className="relationship-list">
                        {Object.entries(relationships).map(([key, name]) => {
                          const cs = run.cases.filter((c) => c.profile === key);
                          const matched = cs.filter(
                            (c) => c.effective_status === "MATCHED",
                          ).length;
                          return (
                            <button
                              key={key}
                              onClick={() => {
                                setProfile(key);
                                setPage("Reconciliation");
                              }}
                            >
                              <div className="relationship-icon">
                                <Layers size={20} />
                              </div>
                              <div>
                                <strong>{name}</strong>
                                <small>
                                  {matched} accepted / {cs.length} relationships
                                </small>
                                <div className="progress-track">
                                  <span
                                    style={{
                                      width: (matched / cs.length) * 100 + "%",
                                    }}
                                  />
                                </div>
                              </div>
                              <span>
                                {Math.round((matched / cs.length) * 100)}%
                              </span>
                              <ChevronRight size={18} />
                            </button>
                          );
                        })}
                      </div>
                      <div className="panel-foot">
                        Evidence scores measure support, not probability of
                        correctness.
                      </div>
                    </section>
                    <section className="panel">
                      <PanelTitle
                        title="Source coverage"
                        subtitle="Records in this run's immutable input snapshot"
                      />
                      <div className="coverage">
                        {[
                          ["Internal ledger", m!.ledger_count],
                          ["Razorpay events", m!.event_count],
                          ["Settlements", m!.settlement_count],
                          ["Bank transactions", m!.bank_count],
                        ].map(([name, n]) => (
                          <div key={name}>
                            <span>{name}</span>
                            <strong>{n}</strong>
                          </div>
                        ))}
                      </div>
                      <div className="coverage-finance">
                        <div>
                          <span>Authoritative settlement net</span>
                          <strong>{currency(m!.expected_settlement)}</strong>
                        </div>
                        <div>
                          <span>Proposed associated bank credits</span>
                          <strong>
                            {currency(m!.associated_bank_credits)}
                          </strong>
                        </div>
                        <div>
                          <span>Automatically confirmed credits</span>
                          <strong>{currency(m!.confirmed_bank_credits)}</strong>
                        </div>
                      </div>
                    </section>
                  </div>
                  <section className="panel">
                    <PanelTitle
                      title="Exceptions to investigate"
                      subtitle="Amount differences and unresolved evidence"
                      action={
                        <button
                          className="text-button"
                          onClick={() => setPage("Review queue")}
                        >
                          View review queue
                          <ArrowUpRight size={15} />
                        </button>
                      }
                    />
                    <CaseTable cases={unresolved.slice(0, 5)} onSelect={open} />
                  </section>
                  <section className="panel recent">
                    <PanelTitle
                      title="Recent runs"
                      subtitle="Source hashes and configuration are saved for reproducibility"
                    />
                    {runs.slice(0, 5).map((r) => (
                      <button
                        key={r.id}
                        className="run-row"
                        onClick={() =>
                          task(async () => {
                            setRun(await api("/runs/" + r.id));
                          })
                        }
                      >
                        <History size={17} />
                        <strong>{r.id.slice(0, 8)}</strong>
                        <span>{label(r.provenance.mode)}</span>
                        <time>
                          {new Date(r.created).toLocaleString("en-IN", {
                            timeZone: "Asia/Kolkata",
                          })}
                        </time>
                        <ChevronRight size={16} />
                      </button>
                    ))}
                  </section>
                </>
              )}
            </>
          )}
          {page === "Import data" && (
            <>
              <div className="callout">
                <FileSpreadsheet size={22} />
                <div>
                  <strong>Four sources. One traceable dataset.</strong>
                  <p>
                    Upload all four CSVs to run your own dataset. Files stay
                    separate from the demo. Dates use YYYY-MM-DD and amounts use
                    rupees; the engine stores paise.
                  </p>
                </div>
              </div>
              <div className="import-grid">
                {sources.map((s) => (
                  <ImportCard
                    key={s}
                    source={s}
                    imported={imports[s]}
                    disabled={busy}
                    required={settings?.required_columns[s] || []}
                    onImport={(file, mapping) =>
                      task(async () => {
                        const form = new FormData();
                        form.append("file", file);
                        form.append("mapping", mapping);
                        const r = await api<Imported>("/imports/" + s, {
                          method: "POST",
                          body: form,
                        });
                        setImports((current) => ({ ...current, [s]: r }));
                      })
                    }
                    onDownload={(path, name) =>
                      task(() => download(path, name))
                    }
                  />
                ))}
              </div>
              <section className="panel import-actions">
                <div>
                  <strong>
                    {Object.keys(imports).length} of 4 sources validated
                  </strong>
                  <p>
                    Rejected rows are preserved in the ingestion report and
                    excluded only with your acknowledgement. Duplicate records
                    remain visible and are quarantined from automatic
                    allocation.
                  </p>
                  {Object.values(imports).some((i) => i.rejected_count > 0) && (
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={ack}
                        onChange={(e) => setAck(e.target.checked)}
                      />
                      I acknowledge the rejected rows and want to reconcile the
                      accepted records.
                    </label>
                  )}
                </div>
                <button
                  className="primary"
                  disabled={
                    busy ||
                    sources.some((s) => !imports[s]) ||
                    (Object.values(imports).some((i) => i.rejected_count > 0) &&
                      !ack)
                  }
                  onClick={() => reconcile(true)}
                >
                  Reconcile uploaded dataset
                  <ArrowRight size={16} />
                </button>
              </section>
            </>
          )}
          {["Reconciliation", "Review queue", "Settlements"].includes(page) && (
            <section className="panel">
              {page === "Reconciliation" && (
                <div className="tabs">
                  {Object.entries(relationships).map(([key, name]) => (
                    <button
                      className={profile === key ? "active" : ""}
                      onClick={() => setProfile(key)}
                      key={key}
                    >
                      {name}
                    </button>
                  ))}
                </div>
              )}
              <div className="table-toolbar">
                <div className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Search records"
                    placeholder="Search IDs, references or evidence…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <select
                  aria-label="Status filter"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                >
                  <option>All statuses</option>
                  {[
                    "MATCHED",
                    "REVIEW",
                    "UNMATCHED",
                    "PARTIAL",
                    "DUPLICATE",
                    "DELAYED",
                    "FAILED",
                  ].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
                <span>{filtered.length} relationships</span>
              </div>
              {!run ? (
                <Empty
                  title="No reconciliation run yet"
                  detail="Run demo reconciliation or import four source files to start."
                />
              ) : filtered.length ? (
                <CaseTable cases={filtered} onSelect={open} />
              ) : (
                <Empty
                  title="No matching records"
                  detail="Try a different search or status filter."
                />
              )}
              <div className="panel-foot">
                Current statuses include manual review. Automated decisions
                remain preserved.
              </div>
            </section>
          )}
          {page === "Reports" && (
            <>
              <div className="callout">
                <Download size={22} />
                <div>
                  <strong>Export the financial trail</strong>
                  <p>
                    CSV reports preserve source IDs, automated decisions and
                    review notes. Monetary fields are labelled in paise.
                    Spreadsheet formula injection is escaped.
                  </p>
                </div>
              </div>
              <div className="report-grid">
                {(settings?.reports || []).map((kind) => (
                  <button
                    className="panel report-card"
                    key={kind}
                    disabled={!run || busy}
                    onClick={() =>
                      task(() =>
                        download(
                          `/runs/${run!.id}/reports/${kind}`,
                          kind + ".csv",
                        ),
                      )
                    }
                  >
                    <FileSpreadsheet size={23} />
                    <div>
                      <strong>{label(kind)}</strong>
                      <small>Download CSV report</small>
                    </div>
                    <Download size={17} />
                  </button>
                ))}
              </div>
              <section className="panel">
                <PanelTitle
                  title="Current review status counts"
                  subtitle="Derived from actual decisions"
                />
                <div className="status-summary">
                  {Object.entries(statusCounts).map(([s, n]) => (
                    <div key={s}>
                      <Badge status={s} />
                      <strong>{n}</strong>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
          {page === "Settings" && (
            <>
              <div className="settings-grid">
                <section className="panel">
                  <PanelTitle
                    title="Gemini investigation"
                    subtitle="Optional explanations; accounting remains deterministic"
                  />
                  <div className="settings-body">
                    <Badge status={settings?.gemini.state || "AI_DISABLED"} />
                    <p>
                      No automatic per-transaction calls. Explicit investigation
                      shares a small evidence summary with Google; configure a
                      model and key on the server before enabling.
                    </p>
                    <dl>
                      <dt>Model</dt>
                      <dd>{settings?.gemini.model}</dd>
                      <dt>Session requests</dt>
                      <dd>
                        {settings?.gemini.requests_used} /{" "}
                        {settings?.gemini.request_limit}
                      </dd>
                    </dl>
                  </div>
                </section>
                <section className="panel">
                  <PanelTitle
                    title="Razorpay integration"
                    subtitle="CSV mode is fully available"
                  />
                  <div className="settings-body">
                    <Badge
                      status={settings?.razorpay.state || "NOT_CONFIGURED"}
                    />
                    <p>{settings?.razorpay.message}</p>
                    <dl>
                      <dt>Credentials configured</dt>
                      <dd>{settings?.razorpay.configured ? "Yes" : "No"}</dd>
                      <dt>Live connection tested</dt>
                      <dd>
                        {settings?.razorpay.connection_tested ? "Yes" : "No"}
                      </dd>
                      <dt>Webhook secret configured</dt>
                      <dd>
                        {settings?.razorpay.webhooks_configured ? "Yes" : "No"}
                      </dd>
                    </dl>
                    <label>
                      Read-only resource
                      <select
                        value={resource}
                        onChange={(e) => setResource(e.target.value)}
                      >
                        <option value="payments">Payments</option>
                        <option value="settlements">Settlements</option>
                        <option value="recon">
                          Settlement reconciliation (month)
                        </option>
                      </select>
                    </label>
                    <label>
                      Start / reconciliation month
                      <input
                        type="date"
                        value={fromDate}
                        onChange={(e) => setFromDate(e.target.value)}
                      />
                    </label>
                    {resource !== "recon" && (
                      <label>
                        End date
                        <input
                          type="date"
                          value={toDate}
                          onChange={(e) => setToDate(e.target.value)}
                        />
                      </label>
                    )}
                    <button
                      className="secondary"
                      disabled={busy || !settings?.razorpay.configured}
                      onClick={() =>
                        task(async () => {
                          const query =
                            resource === "recon"
                              ? {
                                  resource,
                                  year: Number(fromDate.slice(0, 4)),
                                  month: Number(fromDate.slice(5, 7)),
                                }
                              : {
                                  resource,
                                  from_timestamp: Math.floor(
                                    new Date(
                                      fromDate + "T00:00:00+05:30",
                                    ).getTime() / 1000,
                                  ),
                                  to_timestamp: Math.floor(
                                    new Date(
                                      toDate + "T23:59:59+05:30",
                                    ).getTime() / 1000,
                                  ),
                                };
                          setFetchResult(
                            await api("/integrations/razorpay/sync", {
                              method: "POST",
                              body: JSON.stringify(query),
                            }),
                          );
                          await refresh();
                        })
                      }
                    >
                      Fetch live records
                    </button>
                    {fetchResult && (
                      <div className="investigation">
                        <strong>{fetchResult.count} records fetched</strong>
                        <p>{fetchResult.message}</p>
                        <button
                          className="text-button"
                          onClick={() =>
                            task(() =>
                              download(
                                "/integrations/razorpay/fetches/" +
                                  fetchResult.id,
                                "razorpay_raw.csv",
                              ),
                            )
                          }
                        >
                          Download raw report
                          <Download size={14} />
                        </button>
                      </div>
                    )}
                    <p>
                      Raw reports preserve API semantics. Settlement created_at
                      is a creation timestamp, not proof of a bank value date.
                      They are never merged into demo or CSV records
                      automatically.
                    </p>
                  </div>
                </section>
                <section className="panel">
                  <PanelTitle
                    title="Settlement calendar"
                    subtitle="Changes apply to the next run and are recorded"
                  />
                  <div className="settings-body">
                    <label>
                      T+ working days
                      <input
                        type="number"
                        min="0"
                        max="10"
                        value={days}
                        onChange={(e) => setDays(Number(e.target.value))}
                      />
                    </label>
                    <p>
                      {settings?.calendar.source}. No holiday is verified in the
                      built-in demo.
                    </p>
                    <label>
                      Configured holiday evidence (JSON)
                      <textarea
                        value={holidays}
                        onChange={(e) => setHolidays(e.target.value)}
                        rows={4}
                        spellCheck={false}
                      />
                    </label>
                    <small>
                      Each date requires verified: true, source and verified_at
                      to affect working days. Use only documented local
                      evidence.
                    </small>
                    <p>Currency: INR · Timezone: Asia/Kolkata</p>
                  </div>
                </section>
                <section className="panel">
                  <PanelTitle
                    title="Evidence policy"
                    subtitle="Scores are indicators, never calibrated probabilities"
                  />
                  <div className="settings-body">
                    {Object.entries(
                      (settings?.config.weights || {}) as Record<
                        string,
                        Record<string, number>
                      >,
                    ).map(([p, weights]) => (
                      <div className="policy" key={p}>
                        <strong>{relationships[p]}</strong>
                        {Object.entries(weights).map(([name, weight]) => (
                          <div key={name}>
                            <span>{label(name)}</span>
                            <span>{Math.round(weight * 100)}%</span>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </section>
              </div>
              <section className="panel">
                <PanelTitle
                  title="Local access"
                  subtitle="This demonstration is served on loopback; it has no multi-user identity system"
                />
                <div className="settings-body">
                  <label>
                    Optional session access token
                    <input
                      type="password"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <button
                    className="secondary"
                    onClick={() => {
                      sessionStorage.setItem("recon-token", token);
                      task(async () => {
                        await refresh();
                        setNotice("Session access setting saved.");
                      });
                    }}
                  >
                    Save session setting
                  </button>
                  <p>{settings?.security}</p>
                  {run && (
                    <details>
                      <summary>
                        Current run configuration and source hashes
                      </summary>
                      <pre>
                        {JSON.stringify(
                          {
                            configuration: run.config,
                            provenance: run.provenance,
                          },
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  )}
                </div>
              </section>
            </>
          )}
          <footer className="page-footer">
            <span>ClearLedger · Evidence before acceptance</span>
            <span>
              Synthetic data is labelled. Optional services are never assumed
              connected.
            </span>
          </footer>
        </div>
      </main>
      {selected && (
        <div className="drawer-overlay" onClick={() => setSelected(null)}>
          <section
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Match details"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <div className="eyebrow">EVIDENCE WORKSPACE</div>
                <h2>{selected.left.id}</h2>
                <small>{relationships[selected.profile]}</small>
              </div>
              <button
                className="icon-button"
                aria-label="Close details"
                onClick={() => setSelected(null)}
              >
                <X size={22} />
              </button>
            </header>
            <div className="drawer-content">
              <div className="detail-status">
                <Badge status={selected.effective_status} />
                <span>Automated: {label(selected.automated_status)}</span>
              </div>
              <h3>Decision rationale</h3>
              <p>{selected.reason}</p>
              <div className="detail-money">
                <div>
                  <small>Source amount</small>
                  <strong>{currency(selected.left.amount)}</strong>
                </div>
                <div>
                  <small>Candidate amount</small>
                  <strong>
                    {selected.right
                      ? currency(selected.right.amount)
                      : "No allocation"}
                  </strong>
                </div>
                <div>
                  <small>Difference</small>
                  <strong>
                    {selected.evidence
                      ? currency(selected.evidence.difference)
                      : "—"}
                  </strong>
                </div>
                <div>
                  <small>Ledger residual</small>
                  <strong>
                    {selected.profile === "settlement_bank"
                      ? "Not applicable"
                      : currency(selected.residual)}
                  </strong>
                </div>
              </div>
              {selected.evidence && (
                <>
                  <h3>
                    Evidence score · {selected.evidence.score.toFixed(2)} / 100
                  </h3>
                  <p className="muted">
                    Available weights are normalized. Missing evidence is shown
                    below.
                  </p>
                  <div className="evidence-bars">
                    {Object.entries(selected.evidence.breakdown).map(
                      ([key, v]) => (
                        <div key={key}>
                          <span>{label(key)}</span>
                          <div className="progress-track">
                            <span
                              style={{ width: (v.value ?? 0) * 100 + "%" }}
                            />
                          </div>
                          <strong>
                            {v.value === null
                              ? "Unavailable"
                              : Math.round(v.value * 100) + "%"}
                          </strong>
                          <small>
                            Weight {Math.round(v.effective_weight * 100)}%
                          </small>
                        </div>
                      ),
                    )}
                  </div>
                  <div className="evidence-dates">
                    <span>
                      Calendar days:{" "}
                      <strong>{selected.evidence.calendar_days}</strong>
                    </span>
                    <span>
                      Working days:{" "}
                      <strong>{selected.evidence.business_days}</strong>
                    </span>
                  </div>
                  <p>
                    Shared references:{" "}
                    {selected.evidence.shared_references.length
                      ? JSON.stringify(selected.evidence.shared_references)
                      : "None available"}
                  </p>
                  <p>
                    Contradictory fields:{" "}
                    {selected.evidence.contradictions.join(", ") || "None"}
                  </p>
                  <p>
                    Missing evidence:{" "}
                    {selected.evidence.missing_evidence.join(", ") || "None"}
                  </p>
                </>
              )}
              <h3>Source records</h3>
              {[
                ["Source", selected.left],
                ["Allocated candidate", selected.right],
              ].map(
                ([title, record]) =>
                  record && (
                    <details key={String(title)}>
                      <summary>
                        {String(title)} · {(record as Case["left"]).row_id}
                      </summary>
                      <h4>Original values</h4>
                      <pre>
                        {JSON.stringify(
                          (record as Case["left"]).original,
                          null,
                          2,
                        )}
                      </pre>
                      <h4>Normalized values · amounts in paise</h4>
                      <pre>
                        {JSON.stringify(
                          Object.fromEntries(
                            Object.entries(record).filter(
                              ([k]) => k !== "original",
                            ),
                          ),
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  ),
              )}
              {selected.right?.members && (
                <>
                  <h3>Split allocation</h3>
                  {selected.right.members.map((r) => (
                    <div className="candidate" key={r.row_id}>
                      <span>{r.id}</span>
                      <strong>{currency(r.amount)}</strong>
                    </div>
                  ))}
                </>
              )}
              {selected.settlement && (
                <>
                  <h3>Settlement integrity</h3>
                  <div className="coverage-finance">
                    {(
                      [
                        "gross",
                        "fees",
                        "taxes",
                        "refunds",
                        "adjustments",
                        "calculated_net",
                        "authoritative_net",
                        "integrity_difference",
                      ] as const
                    ).map((k) => (
                      <div key={k}>
                        <span>{label(k)}</span>
                        <strong>{currency(selected.settlement![k])}</strong>
                      </div>
                    ))}
                  </div>
                  <p>
                    Expected date:{" "}
                    {selected.settlement.expected_date || "Unavailable"} ·
                    Settlement delay:{" "}
                    {selected.settlement.settlement_delay_business_days ??
                      "Unknown"}{" "}
                    working days
                  </p>
                  {selected.settlement.problems.map((p) => (
                    <p className="warning-text" key={p}>
                      {p}
                    </p>
                  ))}
                  <details>
                    <summary>
                      {selected.settlement.events.length} constituent events
                    </summary>
                    {selected.settlement.events.map((r) => (
                      <div className="candidate" key={r.row_id}>
                        <span>
                          {r.id} · {String(r.event_type)} · {String(r.status)}
                        </span>
                        <strong>{currency(r.amount)}</strong>
                      </div>
                    ))}
                  </details>
                </>
              )}
              <h3>Candidate alternatives</h3>
              {selected.alternatives.length ? (
                selected.alternatives.map((o) => (
                  <div className="candidate" key={o.record.row_id}>
                    <div>
                      <strong>{o.record.id}</strong>
                      <small>
                        {o.record.date} · {currency(o.record.amount)}
                      </small>
                    </div>
                    <span>{o.evidence.score.toFixed(2)} evidence</span>
                  </div>
                ))
              ) : (
                <p>No alternatives found.</p>
              )}
              <h3>Investigation</h3>
              <p>{selected.recommended_action}</p>
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  task(async () => {
                    setExplanation(
                      await api(
                        `/runs/${run!.id}/investigate/${encodeURIComponent(selected.id)}`,
                        { method: "POST" },
                      ),
                    );
                    await refresh();
                  })
                }
              >
                <Sparkles size={16} />
                Investigate evidence
              </button>
              {explanation && (
                <div className="investigation">
                  <strong>
                    {explanation.provider} · {explanation.state}
                  </strong>
                  <p>{explanation.explanation.summary}</p>
                  <p>{explanation.explanation.recommended_action}</p>
                  <small>
                    Sources:{" "}
                    {explanation.explanation.data_sources_used.join(", ")}
                  </small>
                  {explanation.explanation.plausible_explanations.map((p) => (
                    <p key={p}>Hypothesis: {p}</p>
                  ))}
                </div>
              )}
              <h3>Record a review decision</h3>
              {selected.review && (
                <div className="callout compact">
                  <div>
                    <strong>{selected.review.actor}</strong>
                    <p>{selected.review.note}</p>
                  </div>
                </div>
              )}
              <label>
                Reviewer
                <input
                  value={actor}
                  onChange={(e) => setActor(e.target.value)}
                />
              </label>
              <label>
                Reason or note (required)
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Record the evidence supporting your decision…"
                  rows={3}
                />
              </label>
              <div className="review-actions">
                {[
                  ["confirm", "Confirm match"],
                  ["reject", "Reject candidate"],
                  ["partial", "Mark partial"],
                  ["duplicate", "Mark duplicate"],
                  ["unresolved", "Leave unresolved"],
                  ["note", "Add note"],
                ].map(([action, name]) => (
                  <button
                    className={action === "confirm" ? "primary" : "secondary"}
                    disabled={
                      busy ||
                      note.trim().length < 3 ||
                      !actor.trim() ||
                      (["confirm", "partial"].includes(action) &&
                        !selected.right)
                    }
                    onClick={() => decide(action)}
                    key={action}
                  >
                    {name}
                  </button>
                ))}
              </div>
              <p className="muted">
                Manual decisions preserve the original automated result and
                financial difference. Accepting a candidate records your
                judgement; it does not rewrite the source data.
              </p>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
function Stat({
  title,
  value,
  caption,
  color = "",
}: {
  title: string;
  value: string;
  caption: string;
  color?: string;
}) {
  return (
    <div className={"panel stat " + color}>
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{caption}</small>
    </div>
  );
}
function PanelTitle({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel-title">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}
function CaseTable({
  cases,
  onSelect,
}: {
  cases: Case[];
  onSelect: (c: Case) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Source record</th>
            <th>Date</th>
            <th>Amount</th>
            <th>Candidate / reference</th>
            <th>Status</th>
            <th>Evidence</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id} onClick={() => onSelect(c)}>
              <td>
                <button
                  className="record-button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(c);
                  }}
                >
                  {c.left.id}
                </button>
                <small>{relationships[c.profile]}</small>
              </td>
              <td>{c.left.date}</td>
              <td className="amount">{currency(c.left.amount)}</td>
              <td>
                {c.right?.id || "No allocation"}
                <small>
                  {c.left.reference || c.left.name || "Reference unavailable"}
                </small>
              </td>
              <td>
                <Badge status={c.effective_status} />
              </td>
              <td className="score">
                {c.evidence ? c.evidence.score.toFixed(1) : "—"}
                <small>
                  {c.evidence ? "out of 100" : "No assigned candidate"}
                </small>
              </td>
              <td>
                <ChevronRight size={16} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function ImportCard({
  source,
  imported,
  required,
  disabled,
  onImport,
  onDownload,
}: {
  source: string;
  imported?: Imported;
  required: string[];
  disabled: boolean;
  onImport: (file: File, mapping: string) => void;
  onDownload: (path: string, name: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState("{}");
  return (
    <section className="panel import-card">
      <div className="import-title">
        <FileSpreadsheet size={21} />
        <h2>{label(source)}</h2>
        <button
          className="icon-button"
          aria-label={"Download sample " + source}
          onClick={() => onDownload("/samples/" + source, source + ".csv")}
        >
          <Download size={17} />
        </button>
      </div>
      <p>Required: {required.join(", ")}</p>
      <label className="upload-zone">
        <Upload size={24} />
        <strong>{file ? file.name : "Choose CSV file"}</strong>
        <small>UTF-8 · up to 5 MB · no filename is used for storage</small>
        <input
          aria-label={"Upload " + source}
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
      </label>
      <details>
        <summary>Map your column names</summary>
        <p>
          JSON mapping from original headers to canonical fields, for example{" "}
          {JSON.stringify({ "Invoice Number": "id", "Invoice Date": "date" })}.
        </p>
        <textarea
          aria-label={"Column mapping " + source}
          rows={4}
          value={mapping}
          onChange={(e) => setMapping(e.target.value)}
          spellCheck={false}
        />
      </details>
      <button
        className="secondary"
        disabled={!file || disabled}
        onClick={() => file && onImport(file, mapping)}
      >
        Validate and preview
        <ArrowRight size={15} />
      </button>
      {imported && (
        <div className="import-result">
          <div>
            <Badge status={imported.rejected_count ? "REVIEW" : "MATCHED"} />
            <span>
              {imported.accepted} accepted · {imported.rejected_count} rejected
              · {imported.duplicate_count} duplicate rows
            </span>
          </div>
          {imported.rejected.map((r) => (
            <p key={r.line} className="warning-text">
              Line {r.line}: {r.error}
            </p>
          ))}
          {imported.warnings.map((r) => (
            <p key={r.row_id} className="warning-text">
              {r.row_id}: {r.error}
            </p>
          ))}
          <details open>
            <summary>Preview accepted records</summary>
            <div className="preview-scroll">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Date</th>
                    <th>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {imported.records.slice(0, 5).map((r) => (
                    <tr key={r.row_id}>
                      <td>{r.id}</td>
                      <td>{r.date}</td>
                      <td>{currency(r.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <button
            className="text-button"
            onClick={() =>
              onDownload(
                `/imports/${imported.id}/report`,
                source + "_ingestion.csv",
              )
            }
          >
            Download ingestion report
            <Download size={14} />
          </button>
        </div>
      )}
    </section>
  );
}
