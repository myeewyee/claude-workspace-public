# Vault-wide wiki-link rename script
# Renames files and updates all [[wiki-link]] references across the entire vault.
#
# Usage:
#   Single rename (dry-run):  .\rename-links.ps1 "Old Name" "New Name"
#   Single rename (apply):    .\rename-links.ps1 "Old Name" "New Name" -Execute
#   Batch rename (dry-run):   .\rename-links.ps1 -Manifest .scripts\renames.json
#   Batch rename (apply):     .\rename-links.ps1 -Manifest .scripts\renames.json -Execute
#   Links only (skip file rename): .\rename-links.ps1 "Old Name" "New Name" -LinksOnly -Execute

param(
    [string]$Old,
    [string]$New,
    [string]$Manifest,
    [switch]$Execute,
    [switch]$LinksOnly
)

# --- Config ---
$VaultRoot = "<your-vault-path>"
$SkipDirs = @('.obsidian', '.trash', '.git', '.venv', 'node_modules', '.mcp-server')

# --- Input validation ---
$hasPositional = ($Old -and $New)
$hasManifest = [bool]$Manifest

if (-not $hasPositional -and -not $hasManifest) {
    Write-Host "Error: Provide either (Old + New) or -Manifest path." -ForegroundColor Red
    Write-Host ""
    Write-Host "Usage:"
    Write-Host '  .\rename-links.ps1 "Old Name" "New Name"'
    Write-Host '  .\rename-links.ps1 -Manifest .scripts\renames.json'
    Write-Host ""
    Write-Host "Flags:"
    Write-Host "  -Execute    Apply changes (default is dry-run preview)"
    Write-Host "  -LinksOnly  Skip file rename, only update links"
    exit 1
}

if ($hasPositional -and $hasManifest) {
    Write-Host "Error: Provide either (Old + New) or -Manifest, not both." -ForegroundColor Red
    exit 1
}

# --- Build rename list ---
if ($hasManifest) {
    if (-not (Test-Path $Manifest)) {
        Write-Host "Error: Manifest file not found: $Manifest" -ForegroundColor Red
        exit 1
    }
    $json = Get-Content -Path $Manifest -Raw | ConvertFrom-Json
    $renames = @()
    foreach ($entry in $json) {
        $renames += @{ Old = $entry.old; New = $entry.new }
    }
    if ($renames.Count -eq 0) {
        Write-Host "Error: Manifest is empty." -ForegroundColor Red
        exit 1
    }
} else {
    $renames = @( @{ Old = $Old; New = $New } )
}

# --- Collect all target files ---
$skipPattern = ($SkipDirs | ForEach-Object { [regex]::Escape($_) }) -join '|'

$allFiles = Get-ChildItem -Path $VaultRoot -Recurse -File |
    Where-Object {
        ($_.Extension -ceq '.md' -or $_.Extension -ceq '.base') -and
        ($_.FullName -notmatch $skipPattern)
    }

Write-Host ""
if (-not $Execute) {
    Write-Host "=== DRY RUN (preview only) ===" -ForegroundColor Cyan
    Write-Host ""
}

$totalFilesAffected = 0
$totalLinksUpdated = 0
$totalFilesRenamed = 0

# --- Process each rename ---
for ($i = 0; $i -lt $renames.Count; $i++) {
    $oldName = $renames[$i].Old
    $newName = $renames[$i].New
    $entryNum = $i + 1

    Write-Host "[$entryNum/$($renames.Count)] `"$oldName`" -> `"$newName`""

    # 1. Find and rename the file (unless -LinksOnly)
    if (-not $LinksOnly) {
        $matchingFiles = $allFiles | Where-Object { $_.BaseName -ceq $oldName }

        if ($matchingFiles.Count -gt 1) {
            Write-Host "  WARNING: Multiple files named '$oldName' found. Skipping file rename." -ForegroundColor Yellow
            foreach ($f in $matchingFiles) {
                Write-Host "    $($f.FullName)" -ForegroundColor Yellow
            }
        } elseif ($matchingFiles.Count -eq 1) {
            $sourceFile = $matchingFiles[0]
            $newPath = Join-Path $sourceFile.DirectoryName "$newName$($sourceFile.Extension)"
            $relativePath = $sourceFile.FullName.Substring($VaultRoot.Length + 1)
            $relativeNewPath = $newPath.Substring($VaultRoot.Length + 1)

            if ($Execute) {
                Rename-Item -Path $sourceFile.FullName -NewName "$newName$($sourceFile.Extension)"
                Write-Host "  File renamed: $relativePath -> $relativeNewPath" -ForegroundColor Green

                # Update H1 heading inside the file
                $content = Get-Content -Path $newPath -Raw
                $oldH1Pattern = [regex]::Escape("# $oldName")
                if ($content -cmatch "^$oldH1Pattern$" -or $content -cmatch "`n$oldH1Pattern$" -or $content -cmatch "`n$oldH1Pattern`n") {
                    $content = $content -creplace "(?m)^(# )$([regex]::Escape($oldName))$", "`$1$newName"
                    Set-Content -Path $newPath -Value $content -NoNewline
                    Write-Host "  H1 heading updated" -ForegroundColor Green
                }
            } else {
                Write-Host "  File rename: $relativePath -> $relativeNewPath"
            }
            $totalFilesRenamed++
        } else {
            Write-Host "  Note: No file named '$oldName' found. Proceeding with link updates only." -ForegroundColor Yellow
        }
    }

    # 2. Update wiki-links across all files
    # Regex matches: optional ! (embed), then [[Old Name, optional #heading or #^blockref, optional |alias, then ]]
    $escapedOld = [regex]::Escape($oldName)
    $linkPattern = "(!?)\[\[$escapedOld(#[^\]|]*)?((\|)[^\]]+)?\]\]"

    $entryFilesAffected = 0
    $entryLinksUpdated = 0

    foreach ($file in $allFiles) {
        $content = Get-Content -Path $file.FullName -Raw
        if (-not $content) { continue }

        $matches = [regex]::Matches($content, $linkPattern)
        if ($matches.Count -eq 0) { continue }

        $entryFilesAffected++
        $entryLinksUpdated += $matches.Count
        $relativePath = $file.FullName.Substring($VaultRoot.Length + 1)

        if ($Execute) {
            $updatedContent = [regex]::Replace($content, $linkPattern, "`${1}[[$newName`${2}`${3}]]")
            Set-Content -Path $file.FullName -Value $updatedContent -NoNewline
            Write-Host "  Updated: $relativePath ($($matches.Count) link$(if ($matches.Count -gt 1) {'s'}))" -ForegroundColor Green
        } else {
            Write-Host "  Would update: $relativePath ($($matches.Count) link$(if ($matches.Count -gt 1) {'s'}))"
        }
    }

    $totalFilesAffected += $entryFilesAffected
    $totalLinksUpdated += $entryLinksUpdated

    if ($entryFilesAffected -eq 0) {
        Write-Host "  No links found for '$oldName'" -ForegroundColor Yellow
    }
    Write-Host ""
}

# --- Summary ---
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "  Renames processed: $($renames.Count)"
Write-Host "  Files renamed: $totalFilesRenamed"
Write-Host "  Files with link updates: $totalFilesAffected"
Write-Host "  Total links updated: $totalLinksUpdated"

if (-not $Execute) {
    Write-Host ""
    Write-Host "This was a dry run. Run again with -Execute to apply changes." -ForegroundColor Yellow
}

Write-Host ""
