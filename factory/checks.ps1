# Replace the placeholder with the target repo's non-interactive CI checks.
# Example for an SDK-style C# solution:
# dotnet restore
# if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# dotnet build -c Release --no-restore
# if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# dotnet test -c Release --no-restore
# if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ErrorActionPreference = 'Stop'
Write-Error 'Configure factory/checks.ps1 with this repository''s validation commands.'
