/**
 * AWS Amplify / Cognito auth configuration and helpers.
 *
 * Call `configureAuth()` once at app start (client.tsx).
 * Use `getAccessToken()` to inject Authorization headers into API calls.
 */

import { Amplify } from "aws-amplify";
import { fetchAuthSession, signIn, signOut, getCurrentUser } from "aws-amplify/auth";

export function configureAuth() {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
        userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
      },
    },
  });
}

/** Returns the current user's JWT access token, or null if not signed in. */
export async function getAccessToken(): Promise<string | null> {
  try {
    const session = await fetchAuthSession();
    return session.tokens?.accessToken?.toString() ?? null;
  } catch {
    return null;
  }
}

/** Returns true if there is a valid signed-in session. */
export async function isAuthenticated(): Promise<boolean> {
  try {
    await getCurrentUser();
    return true;
  } catch {
    return false;
  }
}

export { signIn, signOut };
