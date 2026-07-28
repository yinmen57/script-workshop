# 前端：本机 npm 直接运行（不进 Docker）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\apps\admin"

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

if (-not (Test-Path "node_modules")) {
  npm install
}

# 前端本地启动；API 代理见 VITE_API_PROXY_TARGET
Write-Host "admin local dev; proxy target from VITE_API_PROXY_TARGET"
npm run dev
