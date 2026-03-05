$vaultRoot = "<your-vault-path>\1. Vault"
$dirs = Get-ChildItem $vaultRoot -Directory -Recurse -Depth 1
foreach ($d in $dirs) {
    $files = Get-ChildItem $d.FullName -Filter "*.md" -ErrorAction SilentlyContinue
    $count = ($files | Measure-Object).Count
    if ($count -gt 0) {
        $sample = ($files | Select-Object -First 3 | ForEach-Object { $_.Name }) -join "; "
        Write-Output "$count|$($d.FullName)|$sample"
    }
}
