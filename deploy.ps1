# First publish. Requires: gh auth login.   powershell -ExecutionPolicy Bypass -File deploy.ps1 [-Repo kinri-tools]
param([string]$Repo = "kinri-tools")
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
Set-Location $PSScriptRoot
function Check($step) { if ($LASTEXITCODE -ne 0) { Write-Host "FAILED at: $step (exit $LASTEXITCODE)"; exit 1 } else { Write-Host "OK: $step" } }

$owner = gh api user --jq .login; Check "get user"

gh repo view "$owner/$Repo" --json name 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { gh repo create "$owner/$Repo" --public --description "JGB rate estimator and interest calculators (auto-updated daily)"; Check "create repo" }

$url = "https://github.com/$owner/$Repo.git"
if (git remote) { git remote set-url origin $url } else { git remote add origin $url }
Check "set remote"

git push -u origin HEAD:main; Check "push"

gh api -X POST "repos/$owner/$Repo/pages" -f build_type=workflow 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { gh api -X PUT "repos/$owner/$Repo/pages" -f build_type=workflow 2>$null | Out-Null }
Check "enable pages"

Start-Sleep 5
gh workflow run update.yml --repo "$owner/$Repo" --ref main; Check "start workflow"
Write-Host ""
Write-Host "SITE URL: https://$($owner.ToLower()).github.io/$Repo/   (ready in 2-5 min)"
Write-Host "Status:   gh run list --repo $owner/$Repo --limit 3"
