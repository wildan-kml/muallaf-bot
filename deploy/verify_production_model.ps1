$ErrorActionPreference = "Stop"

$endpoint = "https://muallaf-bot.mwildankamil.workers.dev/api/chat/model-status"
$expectedModel = "gemini-3.5-flash-lite"
$status = Invoke-RestMethod -Uri $endpoint -Method Get -TimeoutSec 120

$status | ConvertTo-Json -Depth 5

if ($status.llm_model -notlike "*$expectedModel*") {
    throw "Model produksi belum memakai $expectedModel. Nilai aktual: $($status.llm_model)"
}
if (-not $status.llm_ready) {
    throw "Model sudah terkonfigurasi tetapi belum siap. Periksa GEMINI_API_KEY pada Modal Secret."
}
if (-not $status.langchain_ready) {
    throw "LangChain belum siap. Periksa log Modal dan dependensi model."
}

Write-Host "Verifikasi berhasil: model produksi aktif dan siap." -ForegroundColor Green
