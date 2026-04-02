# 🌸 Petal 一键部署指南

## 目录

- [项目验证结论](#项目验证结论)
- [环境要求](#环境要求)
- [一键部署](#一键部署)
- [部署验证](#部署验证)
- [服务地址](#服务地址)
- [管理命令](#管理命令)
- [架构说明](#架构说明)
- [常见问题](#常见问题)
- [生产环境部署](#生产环境部署)

---

## 项目验证结论

| 验证项 | 状态 | 说明 |
|--------|------|------|
| 代码完整性 | ✅ 通过 | 后端 Router→Service→Repository 三层架构完整，4 个模块（Auth/防伪/肌肤分析/推广）齐全 |
| 依赖安装 | ✅ 通过 | `requirements.txt` 55 个依赖全部可安装，无冲突 |
| 应用启动 | ✅ 通过 | FastAPI 应用可正常创建和启动，16 个 API 端点注册成功 |
| 单元测试 | ✅ 通过 | **172 个测试全部通过**（0.62s），覆盖防伪查询、肌肤分析、推广模块 |
| Docker 构建 | ✅ 通过 | Dockerfile 构建成功，镜像可正常运行 |
| Docker Compose | ✅ 通过 | 5 个服务（PostgreSQL/Redis/MinIO/Backend/Nginx）全部启动并健康 |
| 数据库初始化 | ✅ 通过 | 7 张表自动创建（users/products/anti_fake_codes/skin_analyses/promotions/coupons/promo_clicks）|
| API 功能验证 | ✅ 通过 | 健康检查、公开接口、JWT 鉴权保护均正常工作 |
| API 文档 | ✅ 通过 | Swagger UI 和 ReDoc 自动生成并可访问 |
| Nginx 网关 | ✅ 通过 | 反向代理正常工作，API 和健康检查端点均可通过网关访问 |

**结论：项目代码质量高，架构清晰，可成功部署运行。**

---

## 环境要求

### 必需

| 软件 | 最低版本 | 验证命令 |
|------|---------|---------|
| Docker | 20.10+ | `docker --version` |
| Docker Compose | 2.0+ (V2) | `docker compose version` |
| curl | any | `curl --version` |

### 端口需求

| 端口 | 服务 | 说明 |
|------|------|------|
| 80 | Nginx | API 网关入口 |
| 8000 | FastAPI | 后端 API（可直连） |
| 5432 | PostgreSQL | 数据库 |
| 6379 | Redis | 缓存 |
| 9000 | MinIO | 对象存储 API |
| 9001 | MinIO | 对象存储控制台 |

### 硬件建议

- **CPU**: 2 核+
- **内存**: 4GB+（推荐 8GB）
- **磁盘**: 10GB+ 可用空间

---

## 一键部署

### 方式一：一键脚本（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/huangyu6572/petally.git
cd petally

# 2. 执行一键部署
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

脚本会自动完成：
1. ✅ 检查 Docker/Docker Compose 是否安装
2. ✅ 检查端口是否可用
3. ✅ 检查磁盘空间
4. ✅ 构建 Backend Docker 镜像
5. ✅ 拉取 PostgreSQL/Redis/MinIO/Nginx 镜像
6. ✅ 启动所有服务（带健康检查等待）
7. ✅ 自动创建数据库表（7 张表）
8. ✅ 验证所有服务健康状态
9. ✅ 打印服务地址和管理命令

### 方式二：手动 Docker Compose

```bash
cd petally/deploy
docker compose -f docker-compose.dev.yml up -d --build
```

---

## 部署验证

部署完成后，可通过以下方式验证：

### 自动验证

```bash
./deploy/deploy.sh health
```

预期输出：
```
━━━ 服务健康检查 ━━━
[✅]    Backend API     ✓  http://localhost:8000/health
[✅]    Nginx Gateway   ✓  http://localhost:80/health
[✅]    API 文档        ✓  http://localhost:8000/docs
[✅]    Promotions API  ✓  http://localhost:8000/api/v1/promotions
[✅]    PostgreSQL      ✓  localhost:5432
[✅]    Redis           ✓  localhost:6379
[✅]    MinIO Console   ✓  http://localhost:9001
[✅]    数据库表        ✓  7 张表已创建

[✅]    所有服务健康检查通过！🎉
```

### 手动验证

```bash
# 健康检查
curl http://localhost:8000/health
# 返回: {"status":"ok","version":"0.1.0"}

# 通过 Nginx 网关
curl http://localhost:80/health
# 返回: {"status":"ok","version":"0.1.0"}

# 推广列表（公开接口）
curl http://localhost:8000/api/v1/promotions
# 返回: {"code":0,"message":"success","data":{"total":0,"items":[]},...}

# 防伪查询（需 JWT，返回 403）
curl -X POST http://localhost:8000/api/v1/anti-fake/verify \
  -H 'Content-Type: application/json' \
  -d '{"code":"TESTCODE1234"}'
# 返回: {"detail":"Not authenticated"}
```

### 运行单元测试

```bash
./deploy/deploy.sh test
# 输出: 172 passed
```

---

## 服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| **API 网关** | http://localhost:80 | Nginx 反向代理 |
| **后端 API** | http://localhost:8000 | FastAPI 直连 |
| **Swagger 文档** | http://localhost:8000/docs | API 交互式文档 |
| **ReDoc 文档** | http://localhost:8000/redoc | API 文档（美观版） |
| **MinIO 控制台** | http://localhost:9001 | 对象存储管理 |
| | | 用户名: `minioadmin` / 密码: `minioadmin` |
| **PostgreSQL** | localhost:5432 | 数据库: `petal` / 用户: `petal` / 密码: `petal_secret` |
| **Redis** | localhost:6379 | 缓存服务 |

---

## 管理命令

```bash
# 查看服务状态
./deploy/deploy.sh status

# 查看实时日志
./deploy/deploy.sh logs

# 健康检查
./deploy/deploy.sh health

# 重启所有服务（含重新构建）
./deploy/deploy.sh restart

# 停止所有服务
./deploy/deploy.sh stop

# 启动所有服务（不重新构建）
./deploy/deploy.sh start

# 运行单元测试
./deploy/deploy.sh test

# 停止并清除所有数据（⚠️ 不可逆）
./deploy/deploy.sh clean
```

---

## 架构说明

### 服务组件

```
┌─────────────────────────────────────────────────────┐
│                   Nginx (:80)                        │
│               API Gateway / 反向代理                  │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────┼────────────────────────────────┐
│            FastAPI Backend (:8000)                    │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌────────┐ │
│  │  Auth   │ │Anti-Fake │ │  AI Skin  │ │ Promo  │ │
│  │ Module  │ │  Module  │ │  Module   │ │ Module │ │
│  └─────────┘ └──────────┘ └───────────┘ └────────┘ │
│           Router → Service → Repository              │
└──────┬──────────────┬────────────────┬──────────────┘
       │              │                │
┌──────┴──┐    ┌──────┴──┐     ┌──────┴──┐
│PostgreSQL│    │  Redis  │     │  MinIO  │
│  (:5432) │    │ (:6379) │     │(:9000/1)│
│ 主数据库  │    │  缓存   │     │对象存储  │
└─────────┘    └─────────┘     └─────────┘
```

### API 端点清单

| 模块 | 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|------|
| 认证 | POST | `/api/v1/auth/wechat-login` | 微信登录 | 否 |
| 认证 | POST | `/api/v1/auth/refresh` | 刷新 Token | 否 |
| 防伪 | POST | `/api/v1/anti-fake/verify` | 防伪码查询 | JWT |
| 防伪 | GET | `/api/v1/anti-fake/history` | 查询历史 | JWT |
| 防伪 | POST | `/api/v1/anti-fake/admin/import` | 批量导入 | JWT |
| 肌肤 | POST | `/api/v1/skin/analyze` | 提交分析 | JWT |
| 肌肤 | GET | `/api/v1/skin/analyze/{id}` | 获取结果 | JWT |
| 肌肤 | GET | `/api/v1/skin/history` | 分析历史 | JWT |
| 肌肤 | GET | `/api/v1/skin/trend` | 肌肤趋势 | JWT |
| 推广 | GET | `/api/v1/promotions` | 活动列表 | 否 |
| 推广 | GET | `/api/v1/promotions/recommend` | 个性化推荐 | JWT |
| 推广 | GET | `/api/v1/promotions/{id}` | 活动详情 | 否 |
| 推广 | POST | `/api/v1/promotions/{id}/claim-coupon` | 领取优惠券 | JWT |
| 推广 | POST | `/api/v1/promotions/{id}/track` | 事件埋点 | JWT |
| 推广 | POST | `/api/v1/promotions/{id}/share` | 生成分享 | JWT |
| 推广 | GET | `/api/v1/promotions/admin/{id}/analytics` | 数据看板 | JWT |
| 运维 | GET | `/health` | 健康检查 | 否 |

### 数据库表结构

| 表名 | 说明 | 主要字段 |
|------|------|---------|
| `users` | 用户表 | openid, nickname, phone |
| `products` | 商品表 | name, brand, category, price, tags |
| `anti_fake_codes` | 防伪码表 | code, code_hash, product_id, status, query_count |
| `skin_analyses` | 肌肤分析表 | user_id, image_url, analysis_result, overall_score |
| `promotions` | 推广活动表 | title, promo_type, discount_value, stock, status |
| `coupons` | 优惠券表 | promotion_id, user_id, discount_type, status |
| `promo_clicks` | 行为埋点表 | promotion_id, user_id, action, source |

---

## 常见问题

### Q: 端口被占用怎么办？

```bash
# 查看占用端口的进程
sudo lsof -i :8000
# 或
sudo ss -tlnp | grep 8000

# 结束占用进程或修改 docker-compose.dev.yml 中的端口映射
```

### Q: Docker 构建失败？

```bash
# 查看详细日志
cd deploy && docker compose -f docker-compose.dev.yml build --no-cache backend

# 检查网络连接（pip 下载依赖需要网络）
```

### Q: 数据库连接失败？

```bash
# 查看 PostgreSQL 日志
docker logs deploy-postgres-1

# 手动测试连接
docker exec -it deploy-postgres-1 psql -U petal -d petal
```

### Q: 如何查看后端日志？

```bash
# 查看所有服务日志
./deploy/deploy.sh logs

# 只看后端日志
cd deploy && docker compose -f docker-compose.dev.yml logs -f backend
```

### Q: 如何重置所有数据？

```bash
./deploy/deploy.sh clean
# 然后重新部署
./deploy/deploy.sh
```

---

## 生产环境部署

生产环境部署需要额外配置：

### 1. 环境变量

```bash
# 复制环境变量模板
cp deploy/.env.example deploy/.env
# 编辑 .env，填写实际值
vi deploy/.env
```

关键配置项：
- `JWT_SECRET_KEY`: 改为随机强密码
- `DATABASE_URL`: 改为生产数据库地址和强密码
- `WECHAT_APP_ID` / `WECHAT_APP_SECRET`: 填写微信小程序凭证
- `OPENAI_API_KEY`: 填写 AI 服务密钥
- `CORS_ORIGINS`: 改为实际域名

### 2. SSL 证书

```bash
# 将 SSL 证书放入 deploy/ssl/ 目录
mkdir -p deploy/ssl
cp your-cert.pem deploy/ssl/cert.pem
cp your-key.pem deploy/ssl/key.pem

# 使用生产版 docker-compose 和 nginx 配置
docker compose -f docker-compose.yml up -d --build
```

### 3. 数据库迁移

生产环境建议使用 Alembic 管理数据库迁移，而非自动 `create_all`：

```bash
cd backend
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 4. 监控

- Sentry SDK 已集成（配置 `SENTRY_DSN` 即可启用）
- 健康检查端点: `GET /health`
- Docker 内置健康检查（已配置）

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `deploy/deploy.sh` | 一键部署脚本 |
| `deploy/docker-compose.dev.yml` | 开发环境编排（5 个服务） |
| `deploy/docker-compose.yml` | 生产环境编排（含 Celery + SSL） |
| `deploy/nginx-dev.conf` | 开发环境 Nginx 配置（HTTP） |
| `deploy/nginx.conf` | 生产环境 Nginx 配置（HTTPS + Rate Limit）|
| `deploy/.env.example` | 环境变量模板 |
| `backend/Dockerfile` | 后端 Docker 镜像定义 |
| `DEPLOYMENT.md` | 本部署指南 |
