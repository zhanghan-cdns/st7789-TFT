# deepseek_detect.ps1 - Trae AI 调用探测（AI 红绿灯）
# 原理：采样 Trae CN 进程网络 IO 速率，对话时流量飙升 → busy，空闲 → idle
# 用法：powershell -ExecutionPolicy Bypass -File deepseek_detect.ps1
# 状态变化时上报到本地 DeepSeek 代理 (deepseek_proxy.py) 的 /report 接口

$PROXY_URL   = "http://127.0.0.1:8888/report"   # 上报地址（与 deepseek_proxy.py 配合）
$SAMPLE_SEC  = 1                                 # 采样间隔（秒）
$BUSY_KB     = 100                               # 判定阈值（KB）
$BUSY_WINDOW = 3                                 # 最近 N 秒累计超过阈值 → busy
$IDLE_WINDOW = 8                                 # 最近 N 秒累计低于阈值 → idle

$samples = New-Object System.Collections.Queue
$state   = $false

Write-Host "[detect] 开始监控 Trae CN 进程网络 IO ..." -ForegroundColor Green
Write-Host "[detect] 上报地址: $PROXY_URL" -ForegroundColor Green

# 预热计数器（速率计数器首次采样不可靠）
for ($i = 0; $i -lt 2; $i++) {
    try { Get-Counter '\Process(Trae CN*)\IO Data Bytes/sec' -ErrorAction Stop | Out-Null } catch { }
    Start-Sleep -Seconds 1
}

while ($true) {
    $total = 0.0
    try {
        $c = Get-Counter '\Process(Trae CN*)\IO Data Bytes/sec' -ErrorAction Stop
        $total = [double](($c.CounterSamples | Measure-Object -Property CookedValue -Sum).Sum)
    } catch {
        $total = 0.0
    }
    [void]$samples.Enqueue($total)
    while ($samples.Count -gt $IDLE_WINDOW) { [void]$samples.Dequeue() }

    $arr        = @($samples.ToArray())
    $n          = $arr.Count
    $startIdx   = [Math]::Max(0, $n - $BUSY_WINDOW)
    $recentBusy = 0.0
    for ($i = $startIdx; $i -lt $n; $i++) { $recentBusy += $arr[$i] }
    $allIdle    = 0.0
    foreach ($v in $arr) { $allIdle += $v }

    $busyBytes = $BUSY_KB * 1024
    $newState  = $state
    if ($allIdle -lt $busyBytes) { $newState = $false }          # 长时间低流量 → 空闲
    elseif ($recentBusy -gt $busyBytes) { $newState = $true }    # 短时间高流量 → 调用中

    if ($newState -ne $state) {
        $state = $newState
        $tag   = $(if ($state) { 'busy' } else { 'idle' })
        $color = $(if ($state) { 'Red' } else { 'Green' })
        $body  = '{"trae_busy": ' + $(if ($state) { 'true' } else { 'false' }) + '}'
        try {
            Invoke-RestMethod -Uri $PROXY_URL -Method Post -Body $body -ContentType 'application/json' | Out-Null
            Write-Host ("[{0}] Trae 状态: {1}  (最近3秒IO {2:N0} B/s)" -f (Get-Date -Format 'HH:mm:ss'), $tag, $recentBusy) -ForegroundColor $color
        } catch {
            Write-Host ("[{0}] 上报失败: {1}" -f (Get-Date -Format 'HH:mm:ss'), $_) -ForegroundColor Yellow
        }
    }
    Start-Sleep -Seconds $SAMPLE_SEC
}
