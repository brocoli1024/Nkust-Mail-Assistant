param([string]$PythonExecutable = 'python', [switch]$PushOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
# Requires explicit NKUST_TEST_POSTGRES_URL and NKUST_PUSH_TEST_DISPOSABLE=yes.
# The Python guard rejects non-loopback, non-disposable names and production targets.
if ($PushOnly) { & $PythonExecutable -m app.push.verify --push-only }
else { & $PythonExecutable -m app.push.verify }
exit $LASTEXITCODE
