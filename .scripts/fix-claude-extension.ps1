# fix-claude-extension.ps1
# Patches the hardcoded Linux CI path in Claude Code VS Code extension
# so it activates correctly on Windows.
#
# Root cause: extension.js contains a baked-in CI build path
#   file:///home/runner/work/claude-cli-internal/claude-cli-internal/build-agent-sdk/sdk.mjs
# which is passed to Module.createRequire(). On Windows, this is not a valid path,
# so the extension crashes on activation before registering any commands.
#
# Fix: Replace the hardcoded path with __filename (the actual extension.js path at runtime).
#
# Usage: Run in PowerShell. No arguments needed.

$extDir = Get-ChildItem "$env:USERPROFILE\.vscode\extensions" -Directory |
    Where-Object { $_.Name -match '^anthropic\.claude-code-' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $extDir) {
    Write-Error "Claude Code extension directory not found in ~/.vscode/extensions/"
    exit 1
}

$extFile = Join-Path $extDir.FullName "extension.js"

if (-not (Test-Path $extFile)) {
    Write-Error "extension.js not found at $extFile"
    exit 1
}

Write-Host "Found extension at: $extFile"

# Read the file
$content = Get-Content $extFile -Raw

# The hardcoded CI path that breaks on Windows
$badPath = "file:///home/runner/work/claude-cli-internal/claude-cli-internal/build-agent-sdk/sdk.mjs"

if ($content -notmatch [regex]::Escape($badPath)) {
    Write-Host "The hardcoded CI path was not found in extension.js."
    Write-Host "Either it has already been patched or a newer version fixed it."
    exit 0
}

# Back up
$backup = "$extFile.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item $extFile $backup
Write-Host "Backup saved to: $backup"

# Replace the hardcoded path with __filename
# createRequire needs a valid absolute path or file URL to resolve modules from.
# __filename is the actual path to extension.js at runtime, which is correct.
$content = $content.Replace($badPath, '"+__filename+"')

# Write patched file
Set-Content $extFile $content -NoNewline
Write-Host "Patched successfully."
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Reload VS Code (Ctrl+Shift+P -> Developer: Reload Window)"
Write-Host "  2. Check that 'Claude Code' appears in the Output channel dropdown"
Write-Host "  3. If it still fails, check Extension Host logs again for the new error"
