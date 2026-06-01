#!/usr/bin/env bash
: <<'BATCH_OLD'
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "LOG_FILE=%SCRIPT_DIR%Logs\update_code.log"
if not exist "%SCRIPT_DIR%Logs" mkdir "%SCRIPT_DIR%Logs"

set "REMOTE_USER=root"
set "REMOTE_HOST=112.126.63.84"
set "REMOTE_DIR=~/k-matrix"
set "SSH_TARGET=%REMOTE_USER%@%REMOTE_HOST%"

set "RC_EMBED_BASE_URL=http://127.0.0.1:8000"
set "RC_EMBED_MODEL=BAAI/bge-small-zh-v1.5"
set "RC_EMBED_TIMEOUT=600"
set "RC_EMBED_BATCH=4"

set "KNOWN_HOSTS=%SCRIPT_DIR%known_hosts"
set "SSH_OPTS=-o UserKnownHostsFile=%KNOWN_HOSTS% -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=8"

set "SSH_IDENTITY="
if exist "%USERPROFILE%\.ssh\id_ed25519" set "SSH_IDENTITY=%USERPROFILE%\.ssh\id_ed25519"
if exist "%USERPROFILE%\.ssh\id_rsa" set "SSH_IDENTITY=%USERPROFILE%\.ssh\id_rsa"
if defined SSH_IDENTITY (
  set "SSH_OPTS=%SSH_OPTS% -i \"%SSH_IDENTITY%\" -o IdentitiesOnly=yes"
)

> "%LOG_FILE%" (
  echo ==================================================
  echo Start: %date% %time%
  echo Script: %~f0
  echo WorkDir: %cd%
  echo ==================================================
)

echo Log: %LOG_FILE%
echo.

pushd "%SCRIPT_DIR%" >nul

echo [0/3] Check dependencies...
where ssh >nul 2>nul || (echo Missing ssh. & goto :fail)
where scp >nul 2>nul || (echo Missing scp. & goto :fail)
where python >nul 2>nul || (echo Missing python. & goto :fail)

echo [0.5/3] Check SSH auth (key/agent)...
ssh %SSH_OPTS% -o BatchMode=yes %SSH_TARGET% "echo AUTH_OK" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo NOTE: SSH needs password. Recommend SSH key + ssh-agent to avoid repeated prompts. >> "%LOG_FILE%"
)

echo [1/3] Package project (zip)...
python "%SCRIPT_DIR%package_deploy.py" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

set "ZIP_FILE="
for /f "usebackq delims=" %%F in (`dir /b /o-n "%SCRIPT_DIR%KnowledgeBaseTool_Deploy_*.zip" 2^>nul`) do (
  set "ZIP_FILE=%%F"
  goto :zip_found
)
:zip_found
if not defined ZIP_FILE (
  echo Packaging finished but no zip found. >> "%LOG_FILE%"
  goto :fail
)

echo [2/3] Upload zip: %ZIP_FILE%
scp %SSH_OPTS% "%SCRIPT_DIR%%ZIP_FILE%" %SSH_TARGET%:%REMOTE_DIR%/ >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail
echo - Upload archive migration script...
if not exist "%SCRIPT_DIR%manual_archive_sync_to_supabase.py" (
  echo Missing manual_archive_sync_to_supabase.py >> "%LOG_FILE%"
  goto :fail
)
scp %SSH_OPTS% "%SCRIPT_DIR%manual_archive_sync_to_supabase.py" %SSH_TARGET%:%REMOTE_DIR%/ >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo [3/3] Remote deploy and restart...
echo - Ensure remote dir...
ssh %SSH_OPTS% %SSH_TARGET% "mkdir -p %REMOTE_DIR%; cd %REMOTE_DIR%; pwd" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Ensure unzip...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if command -v unzip; then echo UNZIP_OK; else if command -v apt-get; then apt-get update -y; apt-get install -y unzip; elif command -v yum; then yum install -y unzip; elif command -v dnf; then dnf install -y unzip; else echo NO_PKG_MANAGER_FOR_UNZIP; exit 1; fi; fi" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Backup runtime sqlite (instance/data.db)...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; mkdir -p backups; if [ -f instance/data.db ]; then TS=$(date +%%Y%%m%%d_%%H%%M%%S); cp -f instance/data.db backups/data.db.$TS.bak; ls -1t backups/data.db.*.bak 2>/dev/null | tail -n +21 | xargs -r rm -f; echo BACKUP_OK backups/data.db.$TS.bak; else echo BACKUP_SKIP_NO_DB; fi" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Unzip package...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; unzip -o '%ZIP_FILE%'" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Verify deployed code...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; echo '--- scoring_logic.py head ---'; head -n 20 scoring_logic.py; echo '--- openai import/usage check (py) ---'; for f in server.py scoring_logic.py llm_score_evaluator.py; do if [ -f $f ]; then echo \"FILE=$f\"; if grep -nF -e 'import openai' -e 'from openai import' -e 'OpenAI' $f; then echo FOUND_OPENAI_USAGE; else echo OK_NO_OPENAI_USAGE; fi; fi; done" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Ensure venv and deps...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if command -v python3 >/dev/null 2>&1; then PY=python3; elif command -v python >/dev/null 2>&1; then PY=python; else if command -v apt-get >/dev/null 2>&1; then apt-get update -y; apt-get install -y python3 python3-venv python3-pip; PY=python3; elif command -v yum >/dev/null 2>&1; then yum install -y python3 python3-pip; PY=python3; elif command -v dnf >/dev/null 2>&1; then dnf install -y python3 python3-pip; PY=python3; else echo PYTHON_MISSING; exit 1; fi; fi; if [ ! -f venv/bin/activate ]; then $PY -m venv venv; fi; if [ -f venv/bin/activate ]; then . venv/bin/activate; if command -v python >/dev/null 2>&1; then PIP_PY=python; else PIP_PY=python3; fi; else PIP_PY=$PY; fi; $PIP_PY -m pip install -U pip setuptools wheel; $PIP_PY -m pip install -r requirements.txt" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Restart service...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if [ -x venv/bin/python ]; then PY=venv/bin/python; elif [ -x venv/bin/python3 ]; then PY=venv/bin/python3; else if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi; fi; echo RESTART_BEGIN; echo PY=$PY; $PY -c 'import server; print(\"IMPORT_OK_BEFORE_START\")'; if [ -f server.pid ]; then read OLD_PID < server.pid; echo OLD_PID=$OLD_PID; kill -TERM $OLD_PID 2>/dev/null || true; fi; if command -v pkill >/dev/null 2>&1; then pkill -TERM -f 'gunicorn.*server:app' 2>/dev/null || true; fi; rm -f server.pid" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if [ -x venv/bin/python ]; then PY=venv/bin/python; elif [ -x venv/bin/python3 ]; then PY=venv/bin/python3; else if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi; fi; echo WAIT_PORT_BEGIN; for i in 1 2 3 4 5 6 7 8 9 10; do $PY -c 'import socket,sys; s=socket.socket(); s.settimeout(0.5); rc=s.connect_ex((\"127.0.0.1\",5000)); s.close(); print(\"PORT_FREE\" if rc!=0 else \"PORT_STILL_IN_USE\"); sys.exit(0 if rc!=0 else 1)'; if [ $? -eq 0 ]; then break; fi; sleep 1; done; echo WAIT_PORT_END; if command -v ss >/dev/null 2>&1; then ss -ltnp | grep -n ':5000' || true; elif command -v netstat >/dev/null 2>&1; then netstat -tlnp 2>/dev/null | grep -n ':5000' || true; fi" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if [ -x venv/bin/python ]; then PY=venv/bin/python; elif [ -x venv/bin/python3 ]; then PY=venv/bin/python3; else if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi; fi; export RC_EMBED_BASE_URL='%RC_EMBED_BASE_URL%'; export RC_EMBED_MODEL='%RC_EMBED_MODEL%'; export RC_EMBED_TIMEOUT='%RC_EMBED_TIMEOUT%'; export RC_EMBED_BATCH='%RC_EMBED_BATCH%'; $PY -m gunicorn -w 2 -b 0.0.0.0:5000 server:app --daemon --pid server.pid --access-logfile server.log --error-logfile server.log --timeout 300 --graceful-timeout 60 --log-level info; sleep 1; echo RESTART_AFTER_START; if [ ! -s server.pid ]; then echo PID_FILE_NOT_FOUND; tail -n 160 server.log; exit 1; fi; read PID < server.pid; echo SPAWNED_PID=$PID; kill -0 $PID 2>/dev/null || (echo MASTER_DEAD; tail -n 160 server.log; exit 1); echo MASTER_ALIVE" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Verify service...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if [ -x venv/bin/python ]; then PY=venv/bin/python; elif [ -x venv/bin/python3 ]; then PY=venv/bin/python3; else if command -v python3; then PY=python3; else PY=python; fi; fi; for i in 1 2 3 4 5 6 7 8 9 10; do $PY -c 'import socket,sys; s=socket.socket(); s.settimeout(1.0); rc=s.connect_ex((\"127.0.0.1\",5000)); s.close(); print(\"PORT_LISTENING\" if rc==0 else \"PORT_NOT_LISTENING\"); sys.exit(0 if rc==0 else 1)'; if [ $? -eq 0 ]; then if [ -s server.pid ]; then read PID < server.pid; echo SERVICE_OK pid=$PID; else echo SERVICE_OK; fi; exit 0; fi; sleep 1; done; echo SERVICE_NOT_RUNNING; echo '--- ls -l server.pid ---'; ls -l server.pid; echo '--- tail server.log ---'; tail -n 240 server.log; echo '--- ps (gunicorn) ---'; if command -v pgrep; then pgrep -af gunicorn; else ps -ef; fi; exit 1" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Enable supabase governance/archive flags...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if command -v python3 >/dev/null 2>&1; then CFGPY=python3; elif command -v python >/dev/null 2>&1; then CFGPY=python; else echo PYTHON_MISSING; exit 1; fi; $CFGPY -c 'import json; p=\"supabase_config.json\"; d=json.load(open(p,\"r\",encoding=\"utf-8\")); d[\"use_supabase_governance\"]=True; d[\"use_supabase_archives\"]=True; json.dump(d, open(p,\"w\",encoding=\"utf-8\"), ensure_ascii=False); print(d)'" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Run archive migration to supabase...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if [ ! -f manual_archive_sync_to_supabase.py ]; then echo MIGRATION_SCRIPT_MISSING; exit 1; fi; if command -v python3 >/dev/null 2>&1; then python3 manual_archive_sync_to_supabase.py; elif command -v python >/dev/null 2>&1; then python manual_archive_sync_to_supabase.py; else echo PYTHON_MISSING; exit 1; fi" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo - Run ops migration to supabase...
ssh %SSH_OPTS% %SSH_TARGET% "cd %REMOTE_DIR%; if [ -f migrate_ops_to_supabase.py ]; then if command -v python3 >/dev/null 2>&1; then python3 migrate_ops_to_supabase.py; elif command -v python >/dev/null 2>&1; then python migrate_ops_to_supabase.py; else echo PYTHON_MISSING; exit 1; fi; else echo OPS_MIGRATION_SCRIPT_MISSING_SKIP; fi" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo.
echo SUCCESS
popd >nul
start "" notepad "%LOG_FILE%"
echo Press any key to close...
pause >nul
exit /b 0

:fail
echo.
echo FAILED. Check log: %LOG_FILE%
popd >nul
start "" notepad "%LOG_FILE%"
echo Press any key to close...
pause >nul
exit /b 1
BATCH_OLD

# macOS-friendly deployment script (replacement for the original .bat)
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/Logs"
LOG_FILE="$LOG_DIR/update_code.log"
mkdir -p "$LOG_DIR"

REMOTE_USER="root"
REMOTE_HOST="112.126.63.84"
REMOTE_DIR="~/k-matrix"
SSH_TARGET="${REMOTE_USER}@${REMOTE_HOST}"

RC_EMBED_BASE_URL="http://127.0.0.1:8000"
RC_EMBED_MODEL="BAAI/bge-small-zh-v1.5"
RC_EMBED_TIMEOUT="600"
RC_EMBED_BATCH="4"

KNOWN_HOSTS="$SCRIPT_DIR/known_hosts"
SSH_OPTS=(-o "UserKnownHostsFile=$KNOWN_HOSTS" -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=8)

SSH_IDENTITY=""
if [[ -f "$HOME/.ssh/id_ed25519" ]]; then
  SSH_IDENTITY="$HOME/.ssh/id_ed25519"
elif [[ -f "$HOME/.ssh/id_rsa" ]]; then
  SSH_IDENTITY="$HOME/.ssh/id_rsa"
fi
if [[ -n "$SSH_IDENTITY" ]]; then
  SSH_OPTS+=(-i "$SSH_IDENTITY" -o IdentitiesOnly=yes)
fi

{
  echo "=================================================="
  echo "Start: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "Script: $0"
  echo "WorkDir: $(pwd)"
  echo "=================================================="
} >"$LOG_FILE"

echo "Log: $LOG_FILE"
echo

fail() {
  local code="${1:-1}"
  echo
  echo "FAILED. Check log: $LOG_FILE"
  if command -v open >/dev/null 2>&1; then
    open "$LOG_FILE" >/dev/null 2>&1 || true
  fi
  exit "$code"
}

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
fi

cd "$SCRIPT_DIR" || fail 1

echo "[0/3] Check dependencies..."
command -v ssh >/dev/null 2>&1 || fail 1
command -v scp >/dev/null 2>&1 || fail 1
[[ -n "$PY" ]] || fail 1

echo "[0.5/3] Check SSH auth (key/agent)..."
if ! ssh "${SSH_OPTS[@]}" -o BatchMode=yes "$SSH_TARGET" "echo AUTH_OK" >>"$LOG_FILE" 2>&1; then
  echo "NOTE: SSH needs password. Recommend SSH key + ssh-agent to avoid repeated prompts." >>"$LOG_FILE"
fi

echo "[1/3] Package project (zip)..."
"$PY" "$SCRIPT_DIR/package_deploy.py" >>"$LOG_FILE" 2>&1 || fail $?

ZIP_FILE="$(ls -1t "$SCRIPT_DIR"/KnowledgeBaseTool_Deploy_*.zip 2>/dev/null | head -n 1 || true)"
ZIP_NAME="$(basename "$ZIP_FILE" 2>/dev/null || true)"
if [[ -z "$ZIP_FILE" || -z "$ZIP_NAME" ]]; then
  echo "Packaging finished but no zip found." >>"$LOG_FILE"
  fail 1
fi

echo "[2/3] Upload zip: $ZIP_NAME"
scp "${SSH_OPTS[@]}" "$ZIP_FILE" "$SSH_TARGET:$REMOTE_DIR/" >>"$LOG_FILE" 2>&1 || fail $?

echo "- Upload archive migration script..."
MANUAL_SCRIPT="$SCRIPT_DIR/manual_archive_sync_to_supabase.py"
[[ -f "$MANUAL_SCRIPT" ]] || { echo "Missing manual_archive_sync_to_supabase.py" >>"$LOG_FILE"; fail 1; }
scp "${SSH_OPTS[@]}" "$MANUAL_SCRIPT" "$SSH_TARGET:$REMOTE_DIR/" >>"$LOG_FILE" 2>&1 || fail $?

echo "[3/3] Remote deploy and restart..."

echo "- Ensure remote dir..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
mkdir -p ~/k-matrix
cd ~/k-matrix
pwd
EOF
then
  fail $?
fi

echo "- Ensure unzip..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if command -v unzip >/dev/null 2>&1; then
  echo UNZIP_OK
else
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y unzip
  elif command -v yum >/dev/null 2>&1; then
    yum install -y unzip
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y unzip
  else
    echo NO_PKG_MANAGER_FOR_UNZIP
    exit 1
  fi
fi
EOF
then
  fail $?
fi

echo "- Backup runtime sqlite (instance/data.db)..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
mkdir -p backups
if [ -f instance/data.db ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  cp -f instance/data.db "backups/data.db.${TS}.bak"
  ls -1t backups/data.db.*.bak 2>/dev/null | tail -n +21 | xargs -r rm -f
  echo "BACKUP_OK backups/data.db.${TS}.bak"
else
  echo BACKUP_SKIP_NO_DB
fi
EOF
then
  fail $?
fi

echo "- Unzip package..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "ZIP_NAME='$ZIP_NAME' bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
unzip -o "$ZIP_NAME"
EOF
then
  fail $?
fi

echo "- Verify deployed code..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
echo '--- scoring_logic.py head ---'
head -n 20 scoring_logic.py
echo '--- openai import/usage check (py) ---'
for f in server.py scoring_logic.py llm_score_evaluator.py; do
  if [ -f "$f" ]; then
    echo "FILE=$f"
    if grep -nF -e 'import openai' -e 'from openai import' -e 'OpenAI' "$f"; then
      echo FOUND_OPENAI_USAGE
    else
      echo OK_NO_OPENAI_USAGE
    fi
  fi
done
EOF
then
  fail $?
fi

echo "- Ensure venv and deps..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip
    PY=python3
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 python3-pip
    PY=python3
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 python3-pip
    PY=python3
  else
    echo PYTHON_MISSING
    exit 1
  fi
fi

if [ ! -f venv/bin/activate ]; then
  "$PY" -m venv venv
fi

if [ -f venv/bin/activate ]; then
  . venv/bin/activate
  if command -v python >/dev/null 2>&1; then
    PIP_PY=python
  else
    PIP_PY=python3
  fi
else
  PIP_PY="$PY"
fi

"$PIP_PY" -m pip install -U pip setuptools wheel
"$PIP_PY" -m pip install -r requirements.txt
EOF
then
  fail $?
fi

echo "- Restart service..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if [ -x venv/bin/python ]; then
  PY=venv/bin/python
elif [ -x venv/bin/python3 ]; then
  PY=venv/bin/python3
else
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    PY=python
  fi
fi

echo RESTART_BEGIN
echo "PY=$PY"
"$PY" -c 'import server; print("IMPORT_OK_BEFORE_START")'

if [ -f server.pid ]; then
  read OLD_PID < server.pid
  echo "OLD_PID=$OLD_PID"
  kill -TERM "$OLD_PID" 2>/dev/null || true
fi

if command -v pkill >/dev/null 2>&1; then
  pkill -TERM -f 'gunicorn.*server:app' 2>/dev/null || true
fi

rm -f server.pid
EOF
then
  fail $?
fi

if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if [ -x venv/bin/python ]; then
  PY=venv/bin/python
elif [ -x venv/bin/python3 ]; then
  PY=venv/bin/python3
else
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    PY=python
  fi
fi

echo WAIT_PORT_BEGIN
for i in 1 2 3 4 5 6 7 8 9 10; do
  "$PY" -c 'import socket,sys; s=socket.socket(); s.settimeout(0.5); rc=s.connect_ex(("127.0.0.1",5000)); s.close(); print("PORT_FREE" if rc!=0 else "PORT_STILL_IN_USE"); sys.exit(0 if rc!=0 else 1)'
  if [ $? -eq 0 ]; then
    break
  fi
  sleep 1
done
echo WAIT_PORT_END

if command -v ss >/dev/null 2>&1; then
  ss -ltnp | grep -n ':5000' || true
elif command -v netstat >/dev/null 2>&1; then
  netstat -tlnp 2>/dev/null | grep -n ':5000' || true
fi
EOF
then
  fail $?
fi

if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "RC_EMBED_BASE_URL='$RC_EMBED_BASE_URL' RC_EMBED_MODEL='$RC_EMBED_MODEL' RC_EMBED_TIMEOUT='$RC_EMBED_TIMEOUT' RC_EMBED_BATCH='$RC_EMBED_BATCH' bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if [ -x venv/bin/python ]; then
  PY=venv/bin/python
elif [ -x venv/bin/python3 ]; then
  PY=venv/bin/python3
else
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    PY=python
  fi
fi

"$PY" -m gunicorn \
  -w 2 \
  -b 0.0.0.0:5000 \
  server:app \
  --daemon \
  --pid server.pid \
  --access-logfile server.log \
  --error-logfile server.log \
  --timeout 300 \
  --graceful-timeout 60 \
  --log-level info

sleep 1
echo RESTART_AFTER_START

if [ ! -s server.pid ]; then
  echo PID_FILE_NOT_FOUND
  tail -n 160 server.log
  exit 1
fi

read PID < server.pid
echo "SPAWNED_PID=$PID"
kill -0 "$PID" 2>/dev/null || (echo MASTER_DEAD; tail -n 160 server.log; exit 1)
echo MASTER_ALIVE
EOF
then
  fail $?
fi

echo "- Verify service..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if [ -x venv/bin/python ]; then
  PY=venv/bin/python
elif [ -x venv/bin/python3 ]; then
  PY=venv/bin/python3
else
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    PY=python
  fi
fi

for i in 1 2 3 4 5 6 7 8 9 10; do
  "$PY" -c 'import socket,sys; s=socket.socket(); s.settimeout(1.0); rc=s.connect_ex(("127.0.0.1",5000)); s.close(); print("PORT_LISTENING" if rc==0 else "PORT_NOT_LISTENING"); sys.exit(0 if rc==0 else 1)'
  if [ $? -eq 0 ]; then
    if [ -s server.pid ]; then
      read PID < server.pid
      echo "SERVICE_OK pid=$PID"
    else
      echo SERVICE_OK
    fi
    exit 0
  fi
  sleep 1
done

echo SERVICE_NOT_RUNNING
echo '--- ls -l server.pid ---'
ls -l server.pid
echo '--- tail server.log ---'
tail -n 240 server.log
echo '--- ps (gunicorn) ---'
if command -v pgrep >/dev/null 2>&1; then
  pgrep -af gunicorn
else
  ps -ef
fi
exit 1
EOF
then
  fail $?
fi

echo "- Enable supabase governance/archive flags..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if command -v python3 >/dev/null 2>&1; then
  CFGPY=python3
elif command -v python >/dev/null 2>&1; then
  CFGPY=python
else
  echo PYTHON_MISSING
  exit 1
fi

"$CFGPY" -c 'import json; p="supabase_config.json"; d=json.load(open(p,"r",encoding="utf-8")); d["use_supabase_governance"]=True; d["use_supabase_archives"]=True; json.dump(d, open(p,"w",encoding="utf-8"), ensure_ascii=False); print(d)'
EOF
then
  fail $?
fi

echo "- Run archive migration to supabase..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if [ ! -f manual_archive_sync_to_supabase.py ]; then
  echo MIGRATION_SCRIPT_MISSING
  exit 1
fi
if command -v python3 >/dev/null 2>&1; then
  python3 manual_archive_sync_to_supabase.py
elif command -v python >/dev/null 2>&1; then
  python manual_archive_sync_to_supabase.py
else
  echo PYTHON_MISSING
  exit 1
fi
EOF
then
  fail $?
fi

echo "- Run ops migration to supabase..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -s" >>"$LOG_FILE" 2>&1 <<'EOF'
cd ~/k-matrix
if [ -f migrate_ops_to_supabase.py ]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 migrate_ops_to_supabase.py
  elif command -v python >/dev/null 2>&1; then
    python migrate_ops_to_supabase.py
  else
    echo PYTHON_MISSING
    exit 1
  fi
else
  echo OPS_MIGRATION_SCRIPT_MISSING_SKIP
fi
EOF
then
  fail $?
fi

echo
echo "SUCCESS"

if command -v open >/dev/null 2>&1; then
  open "$LOG_FILE" >/dev/null 2>&1 || true
fi
