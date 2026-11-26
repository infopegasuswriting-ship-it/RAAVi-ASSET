$ErrorActionPreference = 'Stop'
$port = if ($env:RAAVI_PORT) { [int]$env:RAAVI_PORT } else { 8766 }
$hostAddr = if ($env:RAAVI_HOST) { $env:RAAVI_HOST } else { '127.0.0.1' }
$url = "http://${hostAddr}:$port/"
$healthUrl = "http://${hostAddr}:$port/api/health"

function Test-Raavi {
    try {
        $web = [Net.WebClient]::new()
        $web.Proxy = $null
        return $web.DownloadString($healthUrl).Contains('"ok": true') -or $web.DownloadString($healthUrl).Contains('"ok":true')
    } catch { return $false } finally { if ($web) { $web.Dispose() } }
}

if (Test-Raavi) {
    Start-Process $url
    exit 0
}

$runtime = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (!(Test-Path -LiteralPath $runtime)) {
    $runtime = (Get-Command python -ErrorAction Stop).Source
}

$process = Start-Process -FilePath $runtime -ArgumentList 'server.py' -WorkingDirectory $PSScriptRoot -PassThru -NoNewWindow
try {
    for ($i = 0; $i -lt 40; $i++) {
        if ($process.HasExited) { throw 'RAAVi could not start. Check the server output above.' }
        if (Test-Raavi) {
            Start-Process $url
            Write-Host "RAAVi is running at $url. Keep this window open while using the app."
            $process.WaitForExit()
            exit $process.ExitCode
        }
        Start-Sleep -Milliseconds 250
    }
    throw 'RAAVi did not start in time.'
} finally {
    if (!$process.HasExited) { $process.Kill() }
}
