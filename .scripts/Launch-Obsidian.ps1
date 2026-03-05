# Launch-Obsidian.ps1
# Cleans lastOpenFiles from workspace.json before launching Obsidian.
# This prevents the startup slowdown caused by Obsidian trying to resolve
# nonexistent/binary/temp file paths against the full vault.
#
# Uses regex replacement instead of JSON parse/serialize to preserve
# the exact file structure (sidebar layout, encoding, property order).
# See: tasks/Fix Obsidian slow load time.md

$vaultPath = "<your-vault-path>"
$workspaceFile = Join-Path $vaultPath ".obsidian\workspace.json"

if (Test-Path $workspaceFile) {
    Copy-Item $workspaceFile "$workspaceFile.bak"
    $content = [System.IO.File]::ReadAllText($workspaceFile)
    $content = [regex]::Replace($content, '"lastOpenFiles"\s*:\s*\[[^\]]*\]', '"lastOpenFiles": []')
    [System.IO.File]::WriteAllText($workspaceFile, $content)
}

Start-Process "obsidian://open?vault=<your-vault-name>"
