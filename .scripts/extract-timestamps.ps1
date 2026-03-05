# Extract timestamps from JSONL session logs
param(
    [string]$FilePath,
    [int[]]$LineNumbers
)

$lines = Get-Content $FilePath
foreach ($lineNum in $LineNumbers) {
    $index = $lineNum - 1  # Convert to 0-based index
    if ($index -lt $lines.Count) {
        $json = $lines[$index] | ConvertFrom-Json
        Write-Output "$lineNum : $($json.timestamp)"
    }
}
