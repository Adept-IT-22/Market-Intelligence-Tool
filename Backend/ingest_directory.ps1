# Batch Ingest Directory Script (PowerShell)
# This script ingests all supported files from a directory into the Market Intelligence database

param(
    [Parameter(Mandatory = $true)]
    [string]$InputDir,
    
    [Parameter(Mandatory = $false)]
    [string]$Sectors = "Innovations,Product Development",
    
    [Parameter(Mandatory = $false)]
    [string]$Summary = "Adept Technologies Innovation Projects"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (!(Test-Path $InputDir)) {
    Write-Host "Error: Directory not found: $InputDir" -ForegroundColor Red
    exit 1
}

Write-Host "========================================"
Write-Host "Market Intelligence - Batch Ingestion"
Write-Host "========================================"
Write-Host "Input Directory: $InputDir"
Write-Host "Sectors: $Sectors"
Write-Host "Summary: $Summary"
Write-Host "========================================"
Write-Host ""

# Activate virtual environment if it exists
$VenvPath = Join-Path $ScriptDir "venv\Scripts\Activate.ps1"
if (Test-Path $VenvPath) {
    & $VenvPath
    Write-Host "Virtual environment activated" -ForegroundColor Green
}

# Run the ingest script
$IngestScript = Join-Path $ScriptDir "ingest_data.py"
python $IngestScript --input $InputDir --sectors $Sectors --summary $Summary

Write-Host ""
Write-Host "========================================"
Write-Host "Ingestion completed!" -ForegroundColor Green
Write-Host "========================================"
