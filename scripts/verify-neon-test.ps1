# Interactive local test window. No connection string is stored or printed.
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe -m app.verify_neon_test
Write-Host "Test finished. Keep this window open so the result can be read."
