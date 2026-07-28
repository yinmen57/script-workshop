# 启动后端全套 Docker（基础设施 + API）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "已从 .env.example 复制 .env"
}

docker compose --env-file .env up -d --build
docker compose ps
Write-Host ""
Write-Host "后端已在 Docker 中运行。前端请执行: .\scripts\dev_admin.ps1"
