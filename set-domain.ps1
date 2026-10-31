# Switch the site to a custom domain AFTER the domain is purchased and DNS records are set.
#   powershell -ExecutionPolicy Bypass -File set-domain.ps1 -Domain kinri-tools.jp
param([Parameter(Mandatory)][string]$Domain, [string]$Repo = "kinri-tools/kinri-tools.github.io")
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
function Check($step) { if ($LASTEXITCODE -ne 0) { Write-Host "FAILED at: $step"; exit 1 } else { Write-Host "OK: $step" } }

$a = Resolve-DnsName $Domain -Type A -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -like '185.199.*' }
if (-not $a) { Write-Host "DNS A records for $Domain do not point to GitHub Pages (185.199.108-111.153) yet. Stop."; exit 1 }
Write-Host "OK: DNS points to GitHub Pages"

gh variable set CUSTOM_DOMAIN --repo $Repo --body $Domain; Check "var CUSTOM_DOMAIN"
gh variable set SITE_URL --repo $Repo --body "https://$Domain"; Check "var SITE_URL"
gh api -X PUT "repos/$Repo/pages" -f cname=$Domain | Out-Null; Check "pages cname"
gh workflow run update.yml --repo $Repo --ref main; Check "rebuild"
Write-Host "HTTPS certificate is issued automatically (up to ~1 hour). Then run:"
Write-Host "  gh api -X PUT repos/$Repo/pages -F https_enforced=true"
