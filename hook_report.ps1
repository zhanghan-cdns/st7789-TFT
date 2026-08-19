# hook_report.ps1 - Trae Hook → AI 红绿灯状态上报
# 用法: powershell -ExecutionPolicy Bypass -File hook_report.ps1 busy|idle
# 将 Trae 对话生命周期事件（UserPromptSubmit/Stop/Notification）上报到本地 DeepSeek 代理，
# 并从 stdin 输入中提取当前模型名（model 字段）一并上报。
param([string]$State = 'idle')

# 调试日志：每次被 Trae 调用都记一行，便于确认 Hook 是否触发
Add-Content -Path (Join-Path $PSScriptRoot 'hook_report.log') `
    -Value ("{0} hook called: {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $State) `
    -ErrorAction SilentlyContinue

# 读取 stdin 原始 JSON（Trae Hook 输入），尝试提取 model 字段
$model = ''
try {
    $raw = [Console]::In.ReadToEnd()
    if ($raw -and $raw.Trim()) {
        $j = $raw | ConvertFrom-Json
        if ($j.PSObject.Properties.Name -contains 'model') {
            $model = [string]$j.model
        }
    }
} catch {
    # stdin 解析失败不影响上报
}

$busy = $State -eq 'busy'
$busyStr = $(if ($busy) { 'true' } else { 'false' })
$modelEsc = ($model -replace '\\', '\\\\' -replace '"', '\"')
$body = '{"trae_busy":' + $busyStr + ',"model":"' + $modelEsc + '"}'
try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:8888/report' -Method Post `
        -Body $body -ContentType 'application/json' -TimeoutSec 3 | Out-Null
} catch {
    # 代理未运行时静默失败，不影响 Trae 对话
}
