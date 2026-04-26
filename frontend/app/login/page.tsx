"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/AppShell";
import { AuthStatusResponse, getAuthStatus, loginUser, logoutAdmin } from "../../lib/api";

const AUTH_UPDATED_EVENT = "auth:updated";

function normalizeNextPath(value: string | null) {
  if (!value || !value.startsWith("/")) {
    return "/chat";
  }

  return value;
}

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(
    () => normalizeNextPath(searchParams.get("next")),
    [searchParams]
  );
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [username, setUsername] = useState("Admin");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function loadAuth() {
      try {
        const nextAuthStatus = await getAuthStatus();
        if (!isMounted) {
          return;
        }
        setAuthStatus(nextAuthStatus);
      } catch {
        if (!isMounted) {
          return;
        }
        setAuthStatus(null);
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadAuth();

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      await loginUser(username, password);
      window.dispatchEvent(new Event(AUTH_UPDATED_EVENT));
      router.replace(nextPath);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not sign in with those credentials."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSignOut() {
    await logoutAdmin();
    window.dispatchEvent(new Event(AUTH_UPDATED_EVENT));
    setAuthStatus((current) =>
      current
        ? {
            ...current,
            authenticated: false,
            username: null,
            role: null,
            session_expires_at: null,
          }
        : current
    );
  }

  if (isLoading) {
    return (
      <AppShell contentClassName="p-4 md:p-6">
        <section className="max-w-md rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
          Loading login...
        </section>
      </AppShell>
    );
  }

  if (authStatus && !authStatus.auth_enabled) {
    return (
      <AppShell contentClassName="p-4 md:p-6">
        <section className="max-w-lg rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
            Login
          </p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
            Authentication is off in this environment
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            This environment is running without enforced login. You can continue straight into the app.
          </p>
          <Link
            href={nextPath}
            className="mt-4 inline-flex rounded-lg bg-slate-950 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Continue
          </Link>
        </section>
      </AppShell>
    );
  }

  if (authStatus?.authenticated) {
    return (
      <AppShell contentClassName="p-4 md:p-6">
        <section className="max-w-lg rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
            Login
          </p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
            You are already signed in
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Signed in as <span className="font-medium text-slate-900">{authStatus.username}</span> with the role <span className="font-medium text-slate-900">{authStatus.role}</span>.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => router.replace(nextPath)}
              className="rounded-lg bg-slate-950 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
            >
              Continue
            </button>
            <button
              type="button"
              onClick={() => void handleSignOut()}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              Sign out
            </button>
          </div>
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell contentClassName="p-4 md:p-6">
      <div className="max-w-md">
        <section className="mb-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
            Login
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            Sign in to Local AI OS
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Use a local account to load saved chats and document permissions.
          </p>
        </section>

        <form
          onSubmit={handleSubmit}
          className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
        >
          {error && (
            <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-200">
              {error}
            </div>
          )}

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Username</span>
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Enter username"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-slate-400"
            />
          </label>

          <label className="mt-4 block space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter password"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-slate-400"
            />
          </label>

          <div className="mt-4 flex justify-between gap-2">
            <Link
              href={nextPath}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              Back
            </Link>
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {isSubmitting ? "Signing in..." : "Sign in"}
            </button>
          </div>
        </form>
      </div>
    </AppShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <AppShell contentClassName="p-4 md:p-6">
          <section className="max-w-md rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
            Loading login...
          </section>
        </AppShell>
      }
    >
      <LoginPageContent />
    </Suspense>
  );
}
