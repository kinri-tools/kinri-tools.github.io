# 初回公開: gh auth login 済みであること。  powershell -ExecutionPolicy Bypass -File deploy.ps1 [-Repo kinri-tools]
param([string]$Repo = "kinri-tools")
$ErrorActionPreference = "Stop"
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
Set-Location $PSScriptRoot
$owner = gh api user --jq .login
if (-not (git remote)) { gh repo create "$owner/$Repo" --public --source . --remote origin }
git push -u origin HEAD:main
# Pages を GitHub Actions 配信で有効化(既に有効ならエラーを無視)
try { gh api -X POST "repos/$owner/$Repo/pages" -f build_type=workflow | Out-Null } catch { Write-Host "pages: $_" }
Start-Sleep 5
gh workflow run update.yml --ref main
Write-Host "公開URL: https://$($owner.ToLower()).github.io/$Repo/  (初回反映まで数分)"
Write-Host "進行状況: gh run list --limit 3"
