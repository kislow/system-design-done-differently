#!/usr/bin/env bash
#
# Proves created users outlive the API process. Run it after `docker compose up`.
# This is session 3's definition of done, as something repeatable rather than
# eight manual curl steps.
set -euo pipefail

# compose and .env are resolved relative to the repo root, so the script works
# from any directory.
cd "$(dirname "$0")/.."

# shellcheck source=.env
. ./.env

API="${API:-http://localhost:8000}"
USER_ID="${USER_ID:-4242}"
ADMIN_TOKEN="admin-token"

log() {
    printf '\n== %s\n' "$*"
}

# 000 means the connection failed rather than the API answering.
status() {
    curl -s -o /dev/null -w '%{http_code}' "$@" 2>/dev/null || true
}

expect_status() {
    local want=$1
    local label=$2
    shift 2
    local got
    got=$(status "$@")
    if [ "$got" = "$want" ]; then
        printf '  ok    %s\n' "$label"
        return 0
    fi
    printf '  FAIL  %s: got %s, want %s\n' "$label" "$got" "$want" >&2
    return 1
}

wait_for_api() {
    for _ in $(seq 1 45); do
        if [ "$(status "$API/users/$USER_ID")" != "000" ]; then
            return 0
        fi
        sleep 1
    done
    printf '  FAIL  API did not answer within 45s\n' >&2
    return 1
}

seed_user() {
    curl -s -o /dev/null -X DELETE "$API/users/$USER_ID" \
        -H "Authorization: Bearer $ADMIN_TOKEN" || true
    expect_status 201 "POST /users created $USER_ID" \
        -X POST "$API/users" \
        -H 'content-type: application/json' \
        -d "{\"id\":$USER_ID,\"name\":\"persisted\",\"email\":\"persisted@coderco.io\"}"
}

show_row() {
    docker compose exec -T db \
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -c "select id, name, email from users where id = $USER_ID;"
}

main() {
    log "seed a user"
    wait_for_api
    seed_user
    expect_status 200 "GET /users/$USER_ID" "$API/users/$USER_ID"

    log "replace the API process"
    docker compose restart api
    wait_for_api
    expect_status 200 "GET /users/$USER_ID survived the API restart" "$API/users/$USER_ID"

    log "take the whole stack down and back up, keeping the volume"
    docker compose down
    docker compose up -d
    wait_for_api
    expect_status 200 "GET /users/$USER_ID survived compose down and up" "$API/users/$USER_ID"

    log "the row as Postgres sees it"
    show_row

    log "proven: user $USER_ID outlived both the API process and the stack"
    printf '  only "docker compose down -v" clears it, that deletes the volume\n'
}

main "$@"
