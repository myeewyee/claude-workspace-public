param([string]$SessionId)

$projectDir = "<your-home-dir>\.claude\projects\<your-project-hash>"
$logFile = Join-Path $projectDir "$SessionId.jsonl"

if (-not (Test-Path $logFile)) {
    Write-Host "Session log not found: $logFile"
    exit 1
}

$lines = Get-Content $logFile
Write-Host "Total lines: $($lines.Count)"
Write-Host ""

$types = @{}
foreach ($line in $lines) {
    try {
        $obj = $line | ConvertFrom-Json -ErrorAction Stop
        $t = $obj.type
        if ($types.ContainsKey($t)) { $types[$t]++ } else { $types[$t] = 1 }

        # Look for tool_use in content blocks
        if ($obj.message -and $obj.message.content) {
            foreach ($block in $obj.message.content) {
                if ($block.type -eq "tool_use") {
                    $inputStr = ($block.input | ConvertTo-Json -Compress)
                    if ($inputStr.Length -gt 200) { $inputStr = $inputStr.Substring(0, 200) + "..." }
                    Write-Host "TOOL_USE: $($block.name) -> $inputStr"
                }
                if ($block.type -eq "tool_result") {
                    Write-Host "TOOL_RESULT for: $($block.tool_use_id)"
                }
            }
        }
    } catch {
        # skip unparseable lines
    }
}

Write-Host ""
Write-Host "Event types:"
foreach ($kv in $types.GetEnumerator() | Sort-Object Value -Descending) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}
