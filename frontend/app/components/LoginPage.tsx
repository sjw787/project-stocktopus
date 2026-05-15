import { useState } from "react";
import { signIn, confirmSignIn } from "~/lib/auth";

interface Props {
  onSuccess: () => void;
}

type Step = "sign_in" | "new_password";

export function LoginPage({ onSuccess }: Props) {
  const [step, setStep] = useState<Step>("sign_in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSignIn(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await signIn({ username: email, password });
      if (result.isSignedIn) {
        onSuccess();
      } else if (result.nextStep.signInStep === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED") {
        setStep("new_password");
      } else {
        setError("Sign-in incomplete — additional steps required.");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleNewPassword(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      const result = await confirmSignIn({ challengeResponse: newPassword });
      if (result.isSignedIn) {
        onSuccess();
      } else {
        setError("Could not complete sign-in. Please try again.");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to set new password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: "var(--bg)" }}
    >
      <div
        className="w-full max-w-sm rounded-lg p-8 space-y-6"
        style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
      >
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold" style={{ color: "var(--accent)" }}>
            🐙 Stocktopus
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {step === "sign_in" ? "Sign in to continue" : "Set your new password"}
          </p>
        </div>

        {step === "sign_in" ? (
          <form onSubmit={(e) => void handleSignIn(e)} className="space-y-4">
            <div className="space-y-1">
              <label className="text-sm" style={{ color: "var(--text-muted)" }}>
                Email
              </label>
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2 rounded text-sm outline-none"
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              />
            </div>

            <div className="space-y-1">
              <label className="text-sm" style={{ color: "var(--text-muted)" }}>
                Password
              </label>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 rounded text-sm outline-none"
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              />
            </div>

            {error && (
              <p className="text-sm" style={{ color: "var(--red, #f87171)" }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
              style={{ background: "var(--accent)", color: "#000" }}
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        ) : (
          <form onSubmit={(e) => void handleNewPassword(e)} className="space-y-4">
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              This is your first sign-in. Please set a permanent password.
            </p>

            <div className="space-y-1">
              <label className="text-sm" style={{ color: "var(--text-muted)" }}>
                New password
              </label>
              <input
                type="password"
                required
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-3 py-2 rounded text-sm outline-none"
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              />
            </div>

            <div className="space-y-1">
              <label className="text-sm" style={{ color: "var(--text-muted)" }}>
                Confirm password
              </label>
              <input
                type="password"
                required
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-3 py-2 rounded text-sm outline-none"
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              />
            </div>

            {error && (
              <p className="text-sm" style={{ color: "var(--red, #f87171)" }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
              style={{ background: "var(--accent)", color: "#000" }}
            >
              {loading ? "Setting password…" : "Set password & sign in"}
            </button>

            <button
              type="button"
              onClick={() => { setStep("sign_in"); setError(null); }}
              className="w-full py-1 text-sm"
              style={{ color: "var(--text-muted)" }}
            >
              ← Back to sign in
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
