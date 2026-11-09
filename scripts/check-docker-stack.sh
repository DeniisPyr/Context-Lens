#!/bin/sh
# Checks a running Docker stack through nginx, the way a browser reaches it:
#   docker compose --profile app up -d --build --wait
#   ACCESS_PASSWORD=... scripts/check-docker-stack.sh
# It needs the app's password, and APP_PORT if the app isn't on 8080. It stops at the
# first check that fails. Nothing here calls Gemini, so a fake GEMINI_API_KEY will do:
# uploading a file that fits and asking a question aren't checked.
#
# It logs in until it's turned away, so run it again only after a minute.

set -eu

: "${ACCESS_PASSWORD:?Set ACCESS_PASSWORD to the password of the app.}"
base_url="http://127.0.0.1:${APP_PORT:-8080}"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cookies="$work/cookies"
headers="$work/headers"
body="$work/body"

fail() {
    echo "FAIL: $*" >&2
    if [ -s "$body" ]; then
        echo "The response was:" >&2
        head -c 500 "$body" >&2
        echo >&2
    fi
    exit 1
}

pass() {
    echo "ok: $*"
}

# Sends a request, keeps the headers and body for the checks, and prints the status.
# The arguments go to curl.
request() {
    : >"$headers"
    : >"$body"
    curl -sS -D "$headers" -o "$body" -w '%{http_code}' "$@" ||
        fail "couldn't send a request to $base_url"
}

expect_status() {
    expected=$1
    actual=$2
    what=$3
    [ "$actual" = "$expected" ] || fail "$what: expected $expected, got $actual"
}

has_header() {
    grep -iq "^$1" "$headers"
}

body_has() {
    grep -q "$1" "$body"
}

# Every response should carry these, errors included.
check_security_headers() {
    what=$1
    has_header "X-Content-Type-Options: nosniff" ||
        fail "$what: no X-Content-Type-Options: nosniff"
    has_header "Referrer-Policy: no-referrer" ||
        fail "$what: no Referrer-Policy: no-referrer"
    has_header "X-Frame-Options: DENY" ||
        fail "$what: no X-Frame-Options: DENY"
    has_header "Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'" ||
        fail "$what: no Content-Security-Policy, or not the expected one"
    pass "$what has the security headers"
}

# A JSON error with a detail, which is what the page shows.
check_json_detail() {
    what=$1
    has_header "Content-Type: application/json" || fail "$what: not JSON"
    body_has '"detail": *"' || fail "$what: no detail in the JSON"
}

# The body that logs in with $1, with its quotes and backslashes escaped for JSON.
json_login() {
    printf '%s' "$1" | sed 's/[\\"]/\\&/g; s/^/{"password": "/; s/$/"}/'
}

# The id in the JSON of the last response.
json_id() {
    sed -n 's/.*"id": *"\([^"]*\)".*/\1/p' "$body"
}

status=$(request "$base_url/")
expect_status 200 "$status" "the page"
has_header "Content-Type: text/html" || fail "the page: not HTML"
body_has '<div id="root">' || fail "the page: not the app's page"
pass "the page loads"
check_security_headers "the page"

status=$(request "$base_url/api/health")
expect_status 200 "$status" "GET /api/health"
pass "the API is healthy"

status=$(request "$base_url/api/datasets")
expect_status 401 "$status" "GET /api/datasets without a session"
pass "the API turns away a request without a session"
check_security_headers "the API's 401"

status=$(request -X POST -H 'Content-Type: application/json' \
    --data "$(json_login "not-$ACCESS_PASSWORD")" "$base_url/api/session")
expect_status 401 "$status" "logging in with a wrong password"
pass "a wrong password is turned away"

status=$(request -c "$cookies" -X POST -H 'Content-Type: application/json' \
    --data "$(json_login "$ACCESS_PASSWORD")" "$base_url/api/session")
expect_status 204 "$status" "logging in with the password"
has_header "Set-Cookie: context_lens_session=" || fail "logging in: no session cookie"
pass "the password logs in and sets the session cookie"

status=$(request -b "$cookies" "$base_url/api/datasets")
expect_status 200 "$status" "GET /api/datasets with the session"
pass "the session cookie opens the API"

status=$(request -b "$cookies" -X POST -H 'Content-Type: application/json' \
    --data "{\"name\": \"Docker check $(date +%s)\"}" "$base_url/api/datasets")
expect_status 201 "$status" "creating a dataset"
dataset_id=$(json_id)
[ -n "$dataset_id" ] || fail "creating a dataset: no id in the response"
pass "a dataset can be created"

# 3 MB, three times the backend's limit.
dd if=/dev/zero bs=1000 count=3000 2>/dev/null | tr '\0' 'a' >"$work/big.txt"
upload_url="$base_url/api/datasets/$dataset_id/documents"

status=$(request -b "$cookies" -F "file=@$work/big.txt;type=text/plain" "$upload_url")
expect_status 413 "$status" "uploading 3 MB"
check_json_detail "uploading 3 MB"
pass "a 3 MB upload is refused with a message"
check_security_headers "the 413"

# Without a session the backend would answer 401, but only after Starlette had written
# the whole request to disk. A 413 means nginx refused it first.
status=$(request -F "file=@$work/big.txt;type=text/plain" "$upload_url")
expect_status 413 "$status" "uploading 3 MB without a session"
pass "nginx refuses a 3 MB upload before the backend reads it"

status=$(request -b "$cookies" -X DELETE "$base_url/api/datasets/$dataset_id")
expect_status 204 "$status" "deleting the dataset"

for path in /docs /redoc /openapi.json; do
    request "$base_url$path" >/dev/null
    if grep -iq -e swagger -e redoc -e '"openapi"' "$body"; then
        fail "$path is the backend's, through nginx"
    fi
done
pass "the backend's /docs, /redoc and /openapi.json aren't served"

# The limit allows a few attempts at once, and two of them have been used above, so it
# should turn one away well within 10.
attempt=0
while :; do
    attempt=$((attempt + 1))
    [ "$attempt" -le 10 ] || fail "10 wrong passwords in a row and none turned away with a 429"
    status=$(request -X POST -H 'Content-Type: application/json' \
        --data "$(json_login "not-$ACCESS_PASSWORD")" "$base_url/api/session")
    [ "$status" = 429 ] && break
    expect_status 401 "$status" "logging in with a wrong password"
done
check_json_detail "the 429"
pass "logging in again and again gets a 429 after $attempt attempts"
check_security_headers "the 429"

status=$(request -b "$cookies" -c "$cookies" -X DELETE "$base_url/api/session")
expect_status 204 "$status" "logging out"
has_header "Set-Cookie: context_lens_session=.*Max-Age=0" ||
    fail "logging out: the session cookie isn't expired"
status=$(request -b "$cookies" "$base_url/api/datasets")
expect_status 401 "$status" "GET /api/datasets after logging out"
pass "logging out expires the session cookie"

echo "All checks passed."
