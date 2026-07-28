# 后端：Docker 构建并启动 API（含依赖基础设施）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "已从 .env.example 复制 .env，请按需修改密钥后再启动。"
}

Write-Host "构建并启动后端（Docker）..."
docker compose --env-file .env up -d --build mysql redis qdrant minio minio-init api
docker compose ps
Write-Host ""
$ApiPort = if ($env:APP_PORT) { $env:APP_PORT } else { "42867" }
Write-Host "API: http://127.0.0.1:$ApiPort/api/v1/health"
Write-Host "前端请另开终端执行: .\scripts\dev_admin.ps1"
