# SharePoint Auto-Ingestion helper for Market Intelligence Tool
# This script starts ngrok to expose your local backend to Power Automate

Write-Host "--- Adept Market Intelligence Tool ---" -ForegroundColor Cyan
Write-Host "SharePoint Auto-Ingestion Automation Startup" -ForegroundColor Green

# 1. Check if ngrok is installed
if (!(Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "ngrok not found. Installing via winget..."
    winget install ngrok.ngrok
}

# 2. Start ngrok
Write-Host "Exposing port 8000 to the public internet..." -ForegroundColor Yellow
# Run ngrok directly. Note: This will block the script until ngrok is closed.
ngrok http 8000

# 3. Instructions
Write-Host "----------------------------------------------------" -ForegroundColor Gray
Write-Host "INSTRUCTIONS:" -ForegroundColor White
Write-Host "1. Go to your ngrok dashboard: https://dashboard.ngrok.com/tunnels/agents"
Write-Host "2. Copy your public HTTPS URL (e.g., https://abc123.ngrok-free.app)"
Write-Host "3. Update your Power Automate HTTP trigger with: URL/upload"
Write-Host "4. Any file uploaded to the mapped SharePoint folders will now be automatically indexed."
Write-Host "----------------------------------------------------" -ForegroundColor Gray

Write-Host "Press any key to stop ngrok and exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

Stop-Process -Name "ngrok" -ErrorAction SilentlyContinue
