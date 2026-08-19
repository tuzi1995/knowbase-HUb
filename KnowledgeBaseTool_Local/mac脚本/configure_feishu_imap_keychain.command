#!/usr/bin/env bash
# Store Feishu IMAP credentials in macOS Keychain without exposing them in
# shell history, process arguments, project files, or service logs.
set -euo pipefail

ACCOUNT="knowbase-hub"
EMAIL_SERVICE="com.kmatrix.knowbase-hub.feishu-imap.email"
PASSWORD_SERVICE="com.kmatrix.knowbase-hub.feishu-imap.password"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper requires macOS Keychain." >&2
  exit 1
fi

if [[ ! -x /usr/bin/security ]]; then
  echo "macOS security command was not found." >&2
  exit 1
fi

echo "Enter the Feishu mailbox address at the first Keychain prompt."
echo "Use the Feishu IMAP-specific password, not the normal login password."
/usr/bin/security add-generic-password -a "$ACCOUNT" -s "$EMAIL_SERVICE" -U -w

echo "Enter the Feishu IMAP-specific password at the second Keychain prompt."
/usr/bin/security add-generic-password -a "$ACCOUNT" -s "$PASSWORD_SERVICE" -U -w

if ! /usr/bin/security find-generic-password -a "$ACCOUNT" -s "$EMAIL_SERVICE" -w >/dev/null 2>&1 \
  || ! /usr/bin/security find-generic-password -a "$ACCOUNT" -s "$PASSWORD_SERVICE" -w >/dev/null 2>&1; then
  echo "Keychain verification failed; check both prompts and try again." >&2
  exit 1
fi

echo "Keychain entries saved for KnowBase Hub."
echo "Click '拉取最新邮件' again; a service restart is not required."
