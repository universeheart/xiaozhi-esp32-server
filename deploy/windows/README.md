# Windows Server Docker 部署（二次开发版）

这套部署会从**当前工作区源码**构建三个 `linux/amd64` 镜像，因此 Python、Java、Vue 的本地二次开发都会进入镜像：

| 镜像 | 构建内容 | 运行服务 |
| --- | --- | --- |
| `xiaozhi-custom/server` | `main/xiaozhi-server` 与当前 `requirements.txt` | WebSocket 8000、HTTP 8003 |
| `xiaozhi-custom/manager-api` | `main/manager-api` Maven 编译产物 | Spring Boot API 8002（仅内网） |
| `xiaozhi-custom/manager-web` | `main/manager-web` npm 编译产物 | Nginx Web 80，对外映射 8002 |

MySQL、Redis 使用官方固定大版本镜像。目标 Windows Server 必须运行 **Linux containers**；Windows containers 不能运行这些镜像。

## 1. 构建前检查

在源码根目录执行。先确认所有需要部署的二次开发文件都已保存：

```bash
git status --short
```

特别注意：未提交的修改也会被 `COPY` 进镜像，只要它们没有被 `.dockerignore` 排除。不要用远端仓库提交记录判断镜像内容，应以构建时的当前目录为准。

启动 Docker Desktop，并创建支持 amd64 的 buildx builder：

```bash
docker buildx create --name xiaozhi-builder --driver docker-container --use
docker buildx inspect --bootstrap
```

如果 `xiaozhi-builder` 已存在，执行：

```bash
docker buildx use xiaozhi-builder
```

## 2. 构建包含全部二次开发的镜像

Apple Silicon Mac 与 Windows Server CPU 架构不同，三个命令都必须带 `--platform=linux/amd64`。建议使用唯一版本号，禁止只依赖 `latest`。

### 推荐：一键构建并生成 Windows 离线部署包

在仓库根目录执行：

```bash
./deploy/windows/build-images.sh --tag 20260829
```

脚本会自动：

1. 检查 Docker daemon、buildx 和 Compose。
2. 校验 `compose.yaml`。
3. 构建 server、manager-api、manager-web 三个 `linux/amd64` 镜像。
4. 拉取 amd64 版 MySQL 8.4 和 Redis 7.4。
5. 验证全部镜像架构。
6. 导出离线镜像 tar、SHA-256 校验文件以及 Windows 部署配置。

输出目录默认为：

```text
deploy/windows/release/xiaozhi-windows-amd64-20260829/
```

常用选项：

```bash
# 完全禁用构建缓存
./deploy/windows/build-images.sh --tag 20260829 --no-cache

# 只构建镜像，不导出体积较大的离线 tar
./deploy/windows/build-images.sh --tag 20260829 --skip-export

# 不下载/打包 MySQL 和 Redis（Windows Server 可以联网拉取时）
./deploy/windows/build-images.sh --tag 20260829 --skip-runtime-images
```

### 手动构建

下面命令必须在仓库根目录 `xiaozhi-esp32-server` 执行。`docker buildx build --platform=linux/amd64` 本身不是完整命令；最后的 `.` 是构建上下文，不能省略。

macOS/Linux（可直接逐行复制）：

```bash
export XIAOZHI_IMAGE_TAG=20260829

docker buildx build --platform=linux/amd64 --file=deploy/windows/Dockerfile.server --tag=xiaozhi-custom/server:${XIAOZHI_IMAGE_TAG} --load .
docker buildx build --platform=linux/amd64 --file=deploy/windows/Dockerfile.manager-api --tag=xiaozhi-custom/manager-api:${XIAOZHI_IMAGE_TAG} --load .
docker buildx build --platform=linux/amd64 --file=deploy/windows/Dockerfile.manager-web --tag=xiaozhi-custom/manager-web:${XIAOZHI_IMAGE_TAG} --load .
```

Windows PowerShell（如果选择在 Windows 上构建）：

```powershell
$ImageTag = "20260829"

docker buildx build --platform=linux/amd64 --file=deploy/windows/Dockerfile.server --tag="xiaozhi-custom/server:$ImageTag" --load .
docker buildx build --platform=linux/amd64 --file=deploy/windows/Dockerfile.manager-api --tag="xiaozhi-custom/manager-api:$ImageTag" --load .
docker buildx build --platform=linux/amd64 --file=deploy/windows/Dockerfile.manager-web --tag="xiaozhi-custom/manager-web:$ImageTag" --load .
```

为什么这些镜像会包含二次开发：

- server 在构建时重新安装当前 `requirements.txt`，然后复制完整 `main/xiaozhi-server`，不会只沿用上游依赖。
- manager-api 在镜像内对当前 `src` 执行 Maven package，不使用上游 JAR。
- manager-web 在镜像内对当前 Vue 源码执行 `npm run build`，不使用上游 dist。
- `.dockerignore` 只排除虚拟环境、缓存、运行数据和构建产物；模型源码目录没有被排除，会随 server 镜像进入构建上下文。

检查最终架构和镜像标签：

```bash
docker image inspect xiaozhi-custom/server:${XIAOZHI_IMAGE_TAG} --format '{{.Os}}/{{.Architecture}}'
docker image inspect xiaozhi-custom/manager-api:${XIAOZHI_IMAGE_TAG} --format '{{.Os}}/{{.Architecture}}'
docker image inspect xiaozhi-custom/manager-web:${XIAOZHI_IMAGE_TAG} --format '{{.Os}}/{{.Architecture}}'
```

三行都应输出 `linux/amd64`。

## 3. 导出镜像并传到 Windows Server

联网服务器可以把自定义镜像推送到私有 Registry。离线部署可直接保存为一个 tar：

```bash
docker pull --platform linux/amd64 mysql:8.4
docker pull --platform linux/amd64 redis:7.4-alpine

docker save -o deploy/windows/xiaozhi-windows-amd64-20260829.tar \
  xiaozhi-custom/server:20260829 \
  xiaozhi-custom/manager-api:20260829 \
  xiaozhi-custom/manager-web:20260829 \
  mysql:8.4 \
  redis:7.4-alpine
```

把以下内容复制到 Windows Server，例如 `D:\xiaozhi`：

- `deploy/windows/xiaozhi-windows-amd64-20260829.tar`
- `deploy/windows/compose.yaml`
- `deploy/windows/.env.example`
- `main/xiaozhi-server/config_from_api.yaml`
- `deploy/windows/deploy.ps1`

如果使用一键构建生成的 release 目录，上述文件已经全部包含。复制整个目录到 Windows Server 后，建议直接以管理员 PowerShell 运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy.ps1
```

脚本会自动执行下面第 4～7 节中可自动化的步骤，包括创建 `.env` 和随机密码、复制 `data\.config.yaml`、加载镜像、启动管理端、写入 `server.secret`、启动全部服务、开放防火墙及输出验证日志。首次注册管理员仍需在浏览器完成，脚本会在需要输入 `server.secret` 时暂停。

脚本同时兼容新版 `docker compose` 和 Windows 上独立安装的 `docker-compose.exe`，运行时会自动检测并选择可用命令。

如已提前取得 secret，可直接传入；`PublicHost` 用于生成视觉接口地址：

```powershell
.\deploy.ps1 -ServerSecret "你的server.secret" -PublicHost "192.168.1.20"
```

## 4. Windows Server 初始化

在 PowerShell 中执行：

```powershell
New-Item -ItemType Directory -Force D:\xiaozhi\data | Out-Null
Set-Location D:\xiaozhi
Copy-Item .env.example .env
Copy-Item config_from_api.yaml data\.config.yaml
docker load -i .\xiaozhi-windows-amd64-20260829.tar
```

编辑 `.env`，至少修改：

```dotenv
MYSQL_ROOT_PASSWORD=强随机密码
REDIS_PASSWORD=另一个强随机密码
IMAGE_TAG=20260829
```

密码不要包含空格或 `#`。生产环境不要沿用示例密码。

## 5. 首次启动管理端并取得 server.secret

先只启动数据库、Redis、API 和 Web：

```powershell
docker compose --env-file .env -f compose.yaml up -d mysql redis manager-api manager-web
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs -f manager-api
```

浏览器打开：

```text
http://Windows服务器IP:8002
```

注册管理员，在参数管理中复制 `server.secret`。然后编辑 `D:\xiaozhi\data\.config.yaml`：

```yaml
manager-api:
  url: http://manager-api:8002/xiaozhi
  secret: 刚复制的server.secret
```

容器内不能使用 `127.0.0.1:8002` 访问另一个容器，必须使用 compose 服务名 `manager-api`。

同时检查 `.config.yaml` 的服务监听配置。对外公布的地址应使用 Windows Server 的局域网 IP，而监听 IP 应允许容器接收连接：

```yaml
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
```

## 6. 启动全部服务

```powershell
docker compose --env-file .env -f compose.yaml up -d
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs -f xiaozhi-server
```

开放 Windows 防火墙 TCP 端口：

- `8002`：管理 Web
- `8000`：小智 WebSocket
- `8003`：HTTP/视觉接口

MySQL 3306、Redis 6379、manager-api 8002 不映射到宿主机，无需暴露到外网。

## 7. 验证与常用运维

```powershell
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs --tail 200 manager-api
docker compose --env-file .env -f compose.yaml logs --tail 200 xiaozhi-server
docker compose --env-file .env -f compose.yaml exec redis redis-cli -a "$env:REDIS_PASSWORD" ping
```

更新二次开发版本时，使用新标签重新构建、导出和加载，然后修改 Windows `.env` 中的 `IMAGE_TAG`：

```powershell
docker compose --env-file .env -f compose.yaml up -d --force-recreate
```

数据库、Redis 和上传文件保存在 Docker named volumes 中，重建应用容器不会删除。不要运行 `docker compose down -v`，除非明确要删除全部业务数据。

## 8. 常见问题

### 镜像没有最新代码

确认构建命令最后的 context 是源码根目录的 `.`，并使用新 `IMAGE_TAG`。可以加 `--no-cache` 做一次完全重建：

```bash
docker buildx build --no-cache --platform linux/amd64 ...
```

### `exec format error`

镜像构建成了 arm64。重新使用 `--platform linux/amd64` 构建，并用 `docker image inspect` 检查。

### server 无法访问 manager-api

检查 `.config.yaml` 是否使用 `http://manager-api:8002/xiaozhi`，不要使用 localhost；再执行：

```powershell
docker compose logs --tail 200 manager-api xiaozhi-server
```

### Docker Desktop 没启动

如果构建提示无法连接 Docker API，先启动 Docker Desktop，确认：

```bash
docker version
```

同时出现 Client 和 Server 信息后才能构建。
