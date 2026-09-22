# Starts n8n locally with the Social Shorts custom node and the settings this project needs.
# Usage:  .\start-n8n.ps1        then open http://localhost:5678
$env:N8N_CUSTOM_EXTENSIONS        = "$HOME\.n8n\custom"      # where the Instagram Reels node lives
$env:N8N_PORT                     = "5678"
$env:N8N_HOST                     = "localhost"
$env:N8N_SECURE_COOKIE            = "false"
$env:N8N_RUNNERS_ENABLED          = "true"
$env:NODES_EXCLUDE                = "[]"                     # n8n 2.x hides "Execute Command" by default; the pipeline needs it
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = "false"                  # workflow reads IG_USER_ID / IG_ACCESS_TOKEN / DISCORD_WEBHOOK_URL from $env
$env:N8N_RESTRICT_FILE_ACCESS_TO  = "$PSScriptRoot\pipeline\output"   # Read File node may read rendered videos
$env:N8N_DEFAULT_BINARY_DATA_MODE = "filesystem"             # videos are big; keep them out of the DB
$env:N8N_PAYLOAD_SIZE_MAX         = "512"                    # MB
$env:N8N_DIAGNOSTICS_ENABLED      = "false"
$env:GENERIC_TIMEZONE             = "America/New_York"
if ($env:N8N_PUBLIC_URL) { $env:WEBHOOK_URL = $env:N8N_PUBLIC_URL }   # set when tunnelling (Discord worker needs a public URL)

# Pipeline location, used by the "Prepare job" node
$env:SHORTS_PIPELINE_DIR = "$PSScriptRoot\pipeline"

# Export every KEY=value from pipeline/.env so workflows can use $env.IG_USER_ID etc.
$dotenv = Join-Path $PSScriptRoot "pipeline\.env"
if (Test-Path $dotenv) {
  Get-Content $dotenv | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
      $k = $matches[1]; $v = $matches[2].Trim().Trim('"')
      if ($v -ne '') { Set-Item -Path "env:$k" -Value $v }
    }
  }
}

n8n start
