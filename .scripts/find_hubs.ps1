[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$vaultRoot = '<your-vault-path>\1. Vault'

# Get all markdown files
$allFiles = Get-ChildItem -LiteralPath $vaultRoot -Recurse -Filter '*.md' | Where-Object { $_.FullName -notlike '*\.obsidian*' }

Write-Host "=== FINDING HIGH-CONNECTIVITY NON-TOPIC NOTES ==="
Write-Host "Scoring each file by number of backlinks from other vault files..."
Write-Host ""

$scores = @{}

foreach ($file in $allFiles) {
    $scores[$file.Name] = 0
}

# For efficiency, read each file once and note what it links to
foreach ($sourceFile in $allFiles) {
    $content = Get-Content -LiteralPath $sourceFile.FullName -Raw -ErrorAction SilentlyContinue
    if ($content) {
        $linkMatches = [regex]::Matches($content, '\[\[([^\]|#]+)')
        $linkedNotes = $linkMatches | ForEach-Object { ($_.Groups[1].Value.Trim()) + '.md' } | Sort-Object -Unique

        foreach ($linked in $linkedNotes) {
            if ($scores.ContainsKey($linked)) {
                $scores[$linked]++
            }
        }
    }
}

# Sort by score descending, take top 40
$topNotes = $scores.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 50

Write-Host "Top 50 most-linked notes in vault:"
$rank = 1
foreach ($entry in $topNotes) {
    Write-Host "$rank. ($($entry.Value) backlinks) $($entry.Key)"
    $rank++
}
