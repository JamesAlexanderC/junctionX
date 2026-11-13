# Installing Docker Desktop on macOS

## Requirements

- macOS 13 (Ventura) or newer, recommended
- At least 4 GB of RAM

## 1. Download and install

### Option A: Homebrew (recommended)

```bash
brew install --cask docker
```

### Option B: Manual download

1. Go to <https://www.docker.com/products/docker-desktop/>
2. Download the build for your chip:
   - **Apple Silicon** (M1/M2/M3/M4)
   - **Intel**

   Not sure which you have? Click  → **About This Mac** and check **Chip** / **Processor**.
3. Open the downloaded `Docker.dmg` and drag **Docker** into **Applications**.

## 2. Start Docker

1. Open **Docker** from Applications (or Spotlight: `Cmd + Space` → "Docker").
2. Accept the terms of service and enter your password if asked.
3. You can skip sign-in; a Docker account isn't needed.
4. Wait until the whale icon in the menu bar stops animating. This means the daemon is running.

## 3. Verify the installation

```bash
docker --version
docker compose version
docker run hello-world
```

If `hello-world` prints "Hello from Docker!", you're good to go.

## Troubleshooting

- **`docker: command not found`**: make sure Docker Desktop is running, then open a new terminal window.
- **`Cannot connect to the Docker daemon`**: Docker Desktop isn't running yet. Open it and wait for the whale icon to stop animating.
- **Slow or high memory use**: adjust the limits in Docker Desktop → **Settings → Resources**.

> **Licensing note:** Docker Desktop is free for personal use, education,
> and small businesses (<250 employees and <$10M revenue). Larger
> organisations need a paid subscription.
