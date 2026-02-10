# Power Automate Ingestion Guide

This guide explains how to automatically ingest files from SharePoint into the Market Intelligence Tool using Microsoft Power Automate.

---

## Prerequisites

### Option A: Use Your Staging Server (Recommended for Production)
If your server at `192.168.1.250` has a **public IP** or is behind a properly configured firewall/NAT with port forwarding, use:
- **URL**: `http://<YOUR_PUBLIC_IP>:8000/upload`

### Option B: Use ngrok for Testing
If your server is only accessible locally, use **ngrok** to expose it temporarily:

```powershell
# Install ngrok (one-time)
winget install ngrok.ngrok

# Authenticate (one-time, get token from https://dashboard.ngrok.com/)
ngrok config add-authtoken YOUR_AUTH_TOKEN

# Expose port 8000
ngrok http 8000
```

This will give you a public URL like: `https://abc123.ngrok-free.app`
Use this URL in Power Automate: `https://abc123.ngrok-free.app/upload`

---

## Power Automate Flow Setup

### Step 1: Create a New Flow
1. Go to [Power Automate](https://make.powerautomate.com/)
2. Click **Create** → **Automated cloud flow**
3. Name your flow (e.g., "Ingest New SharePoint Files")

### Step 2: Set the Trigger
1. Search for **"When a file is created (properties only)"** (SharePoint)
2. **Site Address**: Enter your SharePoint site URL, e.g.:
   - `https://adepttechnologiesltd.sharepoint.com/sites/Innovations`
   - Or select from the dropdown if it appears
3. **Library Name**: Select the document library (e.g., "Documents", "Shared Documents")

### Step 3: Get File Content
1. Add action: **"Get file content"** (SharePoint)
2. **Site Address**: Same as above
3. **File Identifier**: Use dynamic content → `Identifier` from the trigger

### Step 4: Send to API
1. Add action: **HTTP**
2. Configure:
   - **Method**: `POST`
   - **URI**: `http://YOUR_SERVER:8000/upload` (or your ngrok URL)
   - **Headers**: Leave empty
   - **Body**: Switch to "Show advanced options" and select:
     - **Body**: File Content (from previous step)
   - OR use this raw format:
     ```
     Content-Type: multipart/form-data
     ```

### Alternative: Use "HTTP with Azure AD" if authentication is needed later.

---

## API Endpoint Details

| Property | Value |
|----------|-------|
| **URL** | `http://<SERVER>:8000/upload` |
| **Method** | `POST` |
| **Content-Type** | `multipart/form-data` |
| **Form Field** | `file` |

### Supported File Types
- Documents: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.xls`, `.md`
- Images (OCR): `.png`, `.jpg`, `.jpeg`, `.webp`
- Max Size: 10MB

### Response (Success)
```json
{
    "success": true,
    "filename": "1707001234_MyDocument.pdf",
    "original_filename": "MyDocument.pdf",
    "size_kb": 1024.5,
    "execution_time": 5.23
}
```

---

## SharePoint Folder Mappings

The following folders are already configured for ingestion:

| Folder | SharePoint Path |
|--------|-----------------|
| Cloud & Business Automation | `30. Cloud & Business Automation - Documents` |
| Marketing | `03. Marketing - General` |
| BD Collateral | `36. BD Collateral - General` |
| Innovations | `Innovations - General` |

---

## Testing the Integration

1. Start ngrok: `ngrok http 8000`
2. Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`)
3. Update your Power Automate flow with this URL
4. Upload a test file to your SharePoint folder
5. Check the flow run history in Power Automate
6. Verify the file appears in the API response and database
