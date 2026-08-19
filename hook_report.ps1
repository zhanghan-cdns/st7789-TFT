# hook_report.ps1 - Trae Hook → AI 红绿灯状态上报
# 用法: powershell -ExecutionPolicy Bypass -File hook_report.ps1 busy|idle
# 将 Trae 对话生命周期事件（UserPromptSubmit/Stop/Notification）上报到本地 DeepSeek 代理
param([string]$State = 'idle')

$busy = $State -eq 'busy'
$body = '{"trae_busy":' + $(if ($busy) { 'true' } else { 'false' }) + '}'
try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:8888/report' -Method Post `
        -Body $body -ContentType 'application/json' -TimeoutSec 3 | Out-Null
} catch {
    # 代理未运行时静默失败，不影响 Trae 对话
}
