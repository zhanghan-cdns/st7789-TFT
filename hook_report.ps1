# hook_report.ps1 - Trae Hook -> AI traffic-light state reporter
# Usage: powershell -ExecutionPolicy Bypass -File hook_report.ps1 busy|idle
# Reports Trae conversation lifecycle events (UserPromptSubmit/Stop/Notification)
# to the local DeepSeek proxy, and extracts the current model name from stdin.
param([string]$State = 'idle')

# Debug log: one line per hook invocation so we can confirm triggering.
Add-Content -Path (Join-Path $PSScriptRoot 'hook_report.log') `
    -Value ("{0} hook called: {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $State) `
    -ErrorAction SilentlyContinue

# Read raw stdin JSON (Trae Hook input) only when stdin is redirected, with a
# short timeout so we never hang waiting for EOF. Extract the model field if any.
$model = ''
try {
    if ([Console]::IsInputRedirected) {
        $task = [Console]::In.ReadToEndAsync()
        if ([System.Threading.Tasks.Task]::WaitAny(@($task, [System.Threading.Tasks.Task]::Delay(800))) -eq 0) {
            $raw = $task.Result
            if ($raw -and $raw.Trim()) {
                $j = $raw | ConvertFrom-Json
                if ($j.PSObject.Properties.Name -contains 'model') {
                    $model = [string]$j.model
                }
            }
        }
    }
}
catch {
    # stdin read failure must not break reporting
}

$busy = ($State -eq 'busy')
$busyStr = 'true'
if (-not $busy) { $busyStr = 'false' }
$modelEsc = $model.Replace('\', '\\').Replace('"', '\"')
$body = '{"trae_busy":' + $busyStr + ',"model":"' + $modelEsc + '"}'
try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:8888/report' -Method Post `
        -Body $body -ContentType 'application/json' -TimeoutSec 3 | Out-Null
}
catch {
    # proxy down: fail silently so Trae chat is never blocked
}
