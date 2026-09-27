/**
 * SuperTokens frontend configuration - the official React SDK.
 *
 * Enabled now: EmailPassword + Session.
 * Designed for but not enabled: EmailVerification, Passwordless, MFA, Passkeys,
 * ThirdParty. Each is an extra entry in `recipeList` plus the matching backend
 * recipe; nothing else in the app changes.
 */
import EmailPassword from "supertokens-auth-react/recipe/emailpassword";
import Session from "supertokens-auth-react/recipe/session";
import type { SuperTokensConfig } from "supertokens-auth-react/lib/build/types";

export const API_DOMAIN = import.meta.env.VITE_API_DOMAIN ?? "http://localhost:8000";
export const WEBSITE_DOMAIN = import.meta.env.VITE_WEBSITE_DOMAIN ?? "http://localhost:5173";

export const SuperTokensConfigObj: SuperTokensConfig = {
  appInfo: {
    appName: "SkyGuard AI",
    apiDomain: API_DOMAIN,
    websiteDomain: WEBSITE_DOMAIN,
    apiBasePath: "/auth",
    websiteBasePath: "/auth",
  },
  recipeList: [
    EmailPassword.init({
      signInAndUpFeature: {
        signUpForm: {
          formFields: [{ id: "name", label: "Full name", placeholder: "Your name", optional: true }],
        },
      },
    }),
    // httpOnly cookie sessions with anti-CSRF; the SDK sends st-auth-mode: cookie.
    Session.init({ sessionTokenFrontendDomain: undefined }),
  ],
};
