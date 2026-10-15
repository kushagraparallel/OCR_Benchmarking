# Authentication and Sessions

## Responsibilities

This domain owns password hashing, access-token issuance and verification, refresh-token rotation, session revocation, and authenticated-user resolution. API routers validate transport input and translate service errors into HTTP responses; persistence operations are delegated to repositories.

## Security design

- Passwords are hashed with Argon2id; plaintext passwords are never persisted or logged.
- Access tokens are signed JWTs with a short lifetime and a session identifier claim. Protected requests verify the signature and ensure the associated session is still active.
- Refresh tokens are high-entropy opaque values. Only SHA-256 hashes are stored in the database.
- Each successful refresh consumes the old token and creates a replacement. Reuse of a consumed token revokes the associated session and its refresh-token family.
- Refresh tokens are delivered in an HttpOnly cookie. The cookie is Secure in production; SameSite is Strict. The frontend must use credentialed requests for refresh/logout.
- Session endpoints are scoped to the authenticated user's ID.

## API operations

- POST /api/v1/auth/register
- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout
- POST /api/v1/auth/logout-all
- GET /api/v1/auth/me
- GET /api/v1/sessions
- DELETE /api/v1/sessions/{session_id}

## Operational notes

Set a unique high-entropy JWT_SECRET_KEY in every deployed environment. Configure trusted CORS_ORIGINS explicitly. HTTPS is required in production. Add rate limiting at the edge before exposing registration/login publicly. Refresh-token reuse revokes the session, not every account session; the user can log in again.
