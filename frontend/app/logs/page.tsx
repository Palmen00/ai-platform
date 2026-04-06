"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AppShell } from "../../components/AppShell";
import { siteConfig } from "../../config/site";
import { AuthStatusResponse, getAuthStatus, getLogs, LogEvent } from "../../lib/api";

type LogsState = {
  events: LogEvent[];
  rawLines: string[];
};

export default function LogsPage() {
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [logs, setLogs] = useState<LogsState>({ events: [], rawLines: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");

  async function loadLogs() {
    setIsLoading(true);
    setError("");

    try {
      const payload = await getLogs();
      setLogs({
        events: payload.events,
        rawLines: payload.raw_lines,
      });
    } catch {
      setError(siteConfig.logs.loadError);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    let isMounted = true;

    async function loadPage() {
      try {
        const nextAuthStatus = await getAuthStatus();
        if (!isMounted) {
          return;
        }
        setAuthStatus(nextAuthStatus);
        if (!nextAuthStatus.auth_enabled || nextAuthStatus.role === "admin") {
          await loadLogs();
        }
      } catch {
        if (isMounted) {
          setAuthStatus(null);
        }
      } finally {
        if (isMounted) {
          setIsAuthLoading(false);
        }
      }
    }

    void loadPage();

    return () => {
      isMounted = false;
    };
  }, []);

  const eventTypes = useMemo(
    () => Array.from(new Set(logs.events.map((event) => event.event_type))).sort(),
    [logs.events]
  );

  const normalizedSearch = search.trim().toLowerCase();

  const filteredEvents = useMemo(() => {
    return logs.events.filter((event) => {
      const matchesStatus =
        statusFilter === "all" || event.status === statusFilter;
      const matchesType =
        typeFilter === "all" || event.event_type === typeFilter;
      const eventText = [
        event.category,
        event.event_type,
        event.status,
        event.actor_username ?? "",
        event.actor_role ?? "",
        event.message,
        JSON.stringify(event.details),
      ]
        .join(" ")
        .toLowerCase();
      const matchesSearch =
        !normalizedSearch || eventText.includes(normalizedSearch);

      return matchesStatus && matchesType && matchesSearch;
    });
  }, [logs.events, normalizedSearch, statusFilter, typeFilter]);

  const filteredRawLines = useMemo(() => {
    return logs.rawLines.filter((line) =>
      !normalizedSearch ? true : line.toLowerCase().includes(normalizedSearch)
    );
  }, [logs.rawLines, normalizedSearch]);

  if (isAuthLoading) {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-10 text-sm text-slate-600 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8">
          Loading logs...
        </section>
      </AppShell>
    );
  }

  if (authStatus?.auth_enabled && authStatus.role !== "admin") {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8 md:py-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            {siteConfig.logs.title}
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
            Admin access required
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
            Logs stay limited to admins because they can expose backend activity, connector state, and debugging details.
          </p>
          <Link
            href="/login?next=/logs"
            className="mt-5 inline-flex rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Open Login
          </Link>
        </section>
      </AppShell>
    );
  }

  function downloadLogs() {
    const payload = {
      exported_at: new Date().toISOString(),
      filters: {
        search,
        status: statusFilter,
        type: typeFilter,
      },
      events: filteredEvents,
      raw_lines: filteredRawLines,
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `local-ai-logs-${new Date()
      .toISOString()
      .replace(/[:.]/g, "-")}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <AppShell contentClassName="p-4 md:p-6 xl:p-8">
      <div className="space-y-6">
        <section className="flex flex-col gap-4 rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:flex-row md:items-end md:justify-between md:px-8 md:py-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              {siteConfig.logs.title}
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
              {siteConfig.logs.title}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">
              {siteConfig.logs.subtitle}
            </p>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              onClick={downloadLogs}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              {siteConfig.logs.downloadButton}
            </button>
            <button
              onClick={() => void loadLogs()}
              disabled={isLoading}
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {siteConfig.logs.refreshButton}
            </button>
          </div>
        </section>

        {error && (
          <div className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
            {error}
          </div>
        )}

        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
          <div className="mb-5">
            <h3 className="text-xl font-semibold tracking-tight text-slate-950">
              {siteConfig.logs.filtersTitle}
            </h3>
          </div>

          <div className="grid gap-4 md:grid-cols-[1.5fr_1fr_1fr]">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">
                {siteConfig.logs.filterSearchLabel}
              </span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={siteConfig.logs.filterSearchPlaceholder}
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
              />
            </label>

            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">
                {siteConfig.logs.filterStatusLabel}
              </span>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
              >
                <option value="all">{siteConfig.logs.filterStatusAll}</option>
                <option value="info">info</option>
                <option value="warning">warning</option>
                <option value="error">error</option>
              </select>
            </label>

            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">
                {siteConfig.logs.filterTypeLabel}
              </span>
              <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
              >
                <option value="all">{siteConfig.logs.filterTypeAll}</option>
                {eventTypes.map((eventType) => (
                  <option key={eventType} value={eventType}>
                    {eventType}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
          <div className="mb-5">
            <h3 className="text-xl font-semibold tracking-tight text-slate-950">
              {siteConfig.logs.eventsTitle}
            </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-y-2">
              <thead>
                <tr className="text-left text-sm text-slate-500">
                  <th className="px-3 py-2">
                    {siteConfig.logs.columns.timestamp}
                  </th>
                  <th className="px-3 py-2">
                    {siteConfig.logs.columns.actor}
                  </th>
                  <th className="px-3 py-2">{siteConfig.logs.columns.type}</th>
                  <th className="px-3 py-2">
                    {siteConfig.logs.columns.status}
                  </th>
                  <th className="px-3 py-2">
                    {siteConfig.logs.columns.message}
                  </th>
                  <th className="px-3 py-2">
                    {siteConfig.logs.columns.details}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.map((event) => (
                  <tr
                    key={`${event.timestamp}-${event.event_type}-${event.message}`}
                    className="rounded-2xl bg-slate-50 align-top text-slate-700 ring-1 ring-slate-200/70"
                  >
                    <td className="px-3 py-3 text-xs text-slate-500">
                      {new Date(event.timestamp).toLocaleString()}
                    </td>
                    <td className="px-3 py-3 text-sm text-slate-600">
                      {event.actor_username ? (
                        <div className="space-y-1">
                          <div className="font-medium text-slate-900">
                            {event.actor_username}
                          </div>
                          <div className="text-xs uppercase tracking-[0.12em] text-slate-400">
                            {event.actor_role ?? event.category}
                          </div>
                        </div>
                      ) : (
                        <span className="text-xs uppercase tracking-[0.12em] text-slate-400">
                          {event.category}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-sm font-medium text-slate-900">
                      {event.event_type}
                    </td>
                    <td className="px-3 py-3 text-sm">
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                          event.status === "error"
                            ? "bg-red-100 text-red-700"
                            : event.status === "warning"
                              ? "bg-amber-100 text-amber-700"
                              : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {event.status}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-sm">{event.message}</td>
                    <td className="px-3 py-3 text-xs text-slate-500">
                      <pre className="whitespace-pre-wrap break-words font-mono">
                        {JSON.stringify(event.details, null, 2)}
                      </pre>
                    </td>
                  </tr>
                ))}

                {!isLoading && filteredEvents.length === 0 && (
                  <tr>
                      <td
                        colSpan={6}
                        className="px-3 py-8 text-center text-slate-500"
                      >
                      {siteConfig.logs.emptyEvents}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-[2rem] border border-slate-200/80 bg-slate-950 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.18)] md:p-8">
          <div className="mb-5">
            <h3 className="text-xl font-semibold tracking-tight text-white">
              {siteConfig.logs.rawTitle}
            </h3>
          </div>

          <div className="max-h-[32rem] overflow-auto rounded-2xl border border-white/10 bg-black/30 p-4 font-mono text-xs leading-6 text-slate-200">
            {filteredRawLines.length > 0 ? (
              filteredRawLines.map((line, index) => (
                <div key={`${index}-${line}`}>{line}</div>
              ))
            ) : (
              <div className="text-slate-400">{siteConfig.logs.emptyRaw}</div>
            )}
          </div>
        </section>
      </div>
    </AppShell>
  );
}
