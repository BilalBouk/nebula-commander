#!/bin/sh
set -e

# The realm's OIDC client secret is injected from the environment (no secret is baked into
# the image). Refuse to start with a missing/placeholder secret so we never provision a
# publicly-known credential (security audit).
case "${NEBULA_COMMANDER_OIDC_CLIENT_SECRET}" in
  ""|"YOUR_KEYCLOAK_CLIENT_SECRET_HERE"|"CHANGE_ME"*)
    echo "FATAL: NEBULA_COMMANDER_OIDC_CLIENT_SECRET is unset or a placeholder. Set a strong random secret." >&2
    exit 1
    ;;
esac

# Substitute env vars in realm JSON (Keycloak does not do this)
if [ -f /opt/keycloak/data/import/nebula-commander-realm.json ]; then
  sed -e "s|\${NEBULA_COMMANDER_PUBLIC_URL}|${NEBULA_COMMANDER_PUBLIC_URL}|g" \
      -e "s|\${NEBULA_COMMANDER_OIDC_CLIENT_SECRET}|${NEBULA_COMMANDER_OIDC_CLIENT_SECRET}|g" \
      /opt/keycloak/data/import/nebula-commander-realm.json > /tmp/realm.json
  mv /tmp/realm.json /opt/keycloak/data/import/nebula-commander-realm.json
fi

# Start mode is configurable so production can run hardened `start` (TLS, strict hostname)
# WITHOUT rebuilding the image. Defaults to start-dev for local use; set KC_START_MODE=start
# and provide KC_HOSTNAME + TLS/proxy settings in production.
KC_START_MODE="${KC_START_MODE:-start-dev}"
if [ "${KC_START_MODE}" = "start-dev" ]; then
  echo "WARNING: Keycloak is running in DEVELOPMENT mode (start-dev): HTTP allowed, hostname not strict. Do NOT use in production. Set KC_START_MODE=start with TLS for production." >&2
fi

exec /opt/keycloak/bin/kc.sh "${KC_START_MODE}" --import-realm
