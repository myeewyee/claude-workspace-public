$vaultPath = "<your-vault-path>"

Write-Output "=== JOURNAL BREAKDOWN ==="
$journalPath = Get-ChildItem -Path "$vaultPath\1. Projects*" -Directory |
    ForEach-Object { Get-ChildItem -Path $_.FullName -Directory -Filter "*Journal*" } |
    Select-Object -First 1 -ExpandProperty FullName

if ($journalPath) {
    Get-ChildItem -Path $journalPath -Directory -Recurse | ForEach-Object {
        $count = (Get-ChildItem -Path $_.FullName -Filter "*.md" -File).Count
        $relPath = $_.FullName.Replace($journalPath + "\", "")
        [PSCustomObject]@{ Notes = $count; Folder = $relPath }
    } | Where-Object { $_.Notes -gt 0 } | Sort-Object Notes -Descending | Format-Table -AutoSize
} else {
    Write-Output "Journal path not found"
}
Write-Output ""

Write-Output "=== TOPICS / MOCs ==="
$mocsPath = Get-ChildItem -Path "$vaultPath\0. Topics*" -Directory | Select-Object -First 1 -ExpandProperty FullName
if ($mocsPath) {
    Get-ChildItem -Path $mocsPath -Filter "*.md" -Recurse | Select-Object Name | Format-Table -AutoSize
} else {
    Write-Output "MOCs path not found"
}
Write-Output ""

Write-Output "=== PERMANENT NOTES STRUCTURE ==="
$permPath = Get-ChildItem -Path "$vaultPath\3. Permanent*" -Directory | Select-Object -First 1 -ExpandProperty FullName
if ($permPath) {
    $permDirs = Get-ChildItem -Path $permPath -Directory
    if ($permDirs.Count -eq 0) {
        $permCount = (Get-ChildItem -Path $permPath -Filter "*.md" -File).Count
        Write-Output "All $permCount notes are flat (no subfolders)"
    } else {
        Get-ChildItem -Path $permPath -Directory | ForEach-Object {
            $count = (Get-ChildItem -Path $_.FullName -Filter "*.md" -Recurse).Count
            [PSCustomObject]@{ Notes = $count; Folder = $_.Name }
        } | Sort-Object Notes -Descending | Format-Table -AutoSize
        $rootCount = (Get-ChildItem -Path $permPath -Filter "*.md" -File).Count
        Write-Output "Root-level notes: $rootCount"
    }
} else {
    Write-Output "Permanent path not found"
}
Write-Output ""

Write-Output "=== PROJECTS & AREAS - DEEP SUBFOLDERS ==="
$projPath = Get-ChildItem -Path "$vaultPath\1. Projects*" -Directory | Select-Object -First 1 -ExpandProperty FullName
if ($projPath) {
    Get-ChildItem -Path $projPath -Directory | ForEach-Object {
        $area = $_.Name
        $subs = Get-ChildItem -Path $_.FullName -Directory -Recurse
        if ($subs.Count -gt 0) {
            $subs | ForEach-Object {
                $count = (Get-ChildItem -Path $_.FullName -Filter "*.md" -File).Count
                $relPath = $_.FullName.Replace($projPath + "\", "")
                [PSCustomObject]@{ Notes = $count; Folder = $relPath }
            }
        }
    } | Where-Object { $_.Notes -gt 0 } | Sort-Object Notes -Descending | Format-Table -AutoSize
}
