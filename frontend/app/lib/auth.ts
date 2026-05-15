/**
 * AWS Amplify / Cognito auth configuration and helpers.
 *
 * Call `configureAuth()` once at app start (client.tsx).
 * Use `getAccessToken()` to inject Authorization headers into API calls.
 */

import { Amplify } from "aws-amplify";
import { fetchAuthSession, signIn, signOut, getCurrentUser, confirmSignIn } from "aws-amplify/auth";

export function configureAuth() {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL,
        userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
      },
    },
  });
}

/**
 * Returns the current user's Cognito ID token, or null if not signed in.
 * API Gateway REST API Cognito User Pools authorizer validates ID tokens.
 */
export async function getAccessToken(): Promise<string | null> {
  try {
    const session = await fetchAuthSession();
    return session.tokens?.idToken?.toString() ?? null;
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

export { signIn, signOut, confirmSignIn };
