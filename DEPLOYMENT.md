# Deployment Guide

This guide explains how to deploy the Market Intelligence application (Frontend, Backend, and Qdrant) to a Linux server (e.g., Ubuntu VPS) using Docker Compose.

## Prerequisites

1.  **A Server**: An Ubuntu 20.04/22.04 server (DigitalOcean Droplet, AWS EC2, etc.).
2.  **Domain Name** (Optional but recommended): Pointed to your server's IP.
3.  **Groq API Key**: You need your API key for the AI features.

## Step 1: Install Docker & Docker Compose

SSH into your server and run:

```bash
# Update repositories
sudo apt update
sudo apt install -y curl git

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker Compose is included in recent Docker versions (docker compose plugin)
# Verify installation
docker --version
docker compose version
```

## Step 2: Clone the Repository

Upload your code to the server. You can do this via Git (recommended) or SCP/SFTP.

```bash
# If using Git
git clone <your-repo-url> market-intelligence
cd market-intelligence
```

## Step 3: Configure Environment Variables

Create a `.env` file in the root directory (where `docker-compose.yml` is) to store secrets.

```bash
nano .env
```

Add your API Key:

```env
GROQ_API_KEY=your_actual_api_key_here
```

*Save (Ctrl+O, Enter) and Exit (Ctrl+X)*

## Step 4: Run the Application

Start all services in the background:

```bash
docker compose up -d --build
```

**What this does:**
1.  Builds the Angular Frontend (production mode).
2.  Builds the Python Backend.
3.  Pull the Qdrant Vector DB image.
4.  Starts everything.
    *   **Frontend** will be listening on **Port 80*** (HTTP).
    *   **Qdrant** will be available internally.
    *   **Backend** will be accessible internally via Nginx.

## Step 5: Verify Deployment

Open your browser and visit your server's IP address:

`http://<your-server-ip>/`

You should see the application login page.

## Step 6: Data Migration (Important!)

Since Qdrant starts empty on the server, you need to migrate your vector data.

1.  **Locate Backup**: On your local machine, a backup was created at:
    `Backend/snapshots/market_intelligence_backup.snapshot`

2.  **Upload to Server**:
    Copy this file to the same path on the server (`market-intelligence/Backend/snapshots/`).
    ```bash
    scp Backend/snapshots/market_intelligence_backup.snapshot user@your-server-ip:~/market-intelligence/Backend/snapshots/
    ```

3.  **Run Restore Script**:
    On the server, run the restore script using the running backend container:
    ```bash
    # This runs the python script INSIDE the docker container
    docker compose exec backend python restore_qdrant.py
    ```

    *If you see "Snapshot successfully uploaded and restored!", you are done.*

## Troubleshooting

-   **View Logs**:
    ```bash
    docker compose logs -f
    ```
-   **Restart Services**:
    ```bash
    docker compose restart
    ```
-   **Rebuild after changes**:
    ```bash
    docker compose up -d --build
    ```

## Persistence

Data is persisted in:
*   **SQLite DB**: Mapped to `./Backend/DB/` on your host machine.
*   **Uploads**: Mapped to `./Backend/uploads/` on your host machine.
*   **Vectors**: Stored in a Docker Volume `qdrant_storage`.
