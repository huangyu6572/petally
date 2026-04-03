# 🌸 Petal 一键部署指南

## 验证结果摘要

| 验证项 | 状态 | 详情 |
|--------|------|------|
| Python 依赖安装 | ✅ 通过 | 所有 55 个依赖包安装成功 |
| FastAPI 应用导入 | ✅ 通过 | `app.main:app` 正常创建 |
| 单元测试 | ✅ 通过 | **172 个测试全部通过** (0.63s) |
| Docker 镜像构建 | ✅ 通过 | `petally-backend` 镜像构建成功 |
| PostgreSQL | ✅ 通过 | v15-alpine，7 张表自动创建 |
| Redis | ✅ 通过 | v7-alpine，PONG 正常响应 |
| MinIO | ✅ 通过 | 控制台 http://localhost:9001 可访问 |
| FastAPI Backend | ✅ 通过 | 4 个 Gunicorn Worker，16 个 API 端点 |
| Nginx Gateway | ✅ 通过 | 反向代理正常工作 |
| API 文档 | ✅ 通过 | Swagger UI + ReDoc 可访问 |
| JWT 鉴权 | ✅ 通过 | 未认证请求正确返回 401 |

---

## 前置条件

| 条件 | 最低要求 |
|------|----------|
| 操作系统 | Linux (Ubuntu 20.04+, CentOS 7+) / macOS |
| Docker | >= 20.10 |
| Docker Compose | >= 2.0 (V2) |
| 内存 | >= 2GB |
| 磁盘 | >= 2GB 可用空间 |
| 端口 | 80, 8000, 5432, 6379, 9000, 9001 |

### 安装 Docker（如未安装）

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# 验证
docker --version
docker compose version
```

---

## 一键部署

### 方式一：使用部署脚本（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/huangyu6572/petally.git
cd petally

# 2. 一键部署
cd deploy
chmod +x deploy.sh
./deploy.sh
```

部署脚本会自动完成：
1. ✅ 检查 Docker / Docker Compose 是否安装
2. ✅ 检查所需端口是否可用
3. ✅ 检查磁盘空间
4. ✅ 构建 Backend Docker 镜像
5. ✅ 启动所有服务（PostgreSQL、Redis、MinIO、Backend、Nginx）
6. ✅ 等待所有服务就绪
7. ✅ 自动创建数据库表
8. ✅ 执行健康检查验证

### 方式二：手动部署

```bash
cd petally/deploy
docker compose -f docker-compose.dev.yml up -d --build
```

---

## 管理命令

```bash
cd petally/deploy

# 启动服务
./deploy.sh start

# 停止服务
./deploy.sh stop

# 重启服务（含重新构建）
./deploy.sh restart

# 查看服务状态
./deploy.sh status

# 查看实时日志
./deploy.sh logs

# 健康检查
./deploy.sh health

# 运行单元测试
./deploy.sh test

# 停止并清除所有数据（⚠️ 不可逆）
./deploy.sh clean
```

---

## 服务地址

部署成功后，以下服务将可用：

| 服务 | 地址 | 说明 |
|------|------|------|
| API Gateway (Nginx) | http://localhost:80 | 反向代理入口 |
| Backend API | http://localhost:8000 | FastAPI 后端直连 |
| Swagger 文档 | http://localhost:8000/docs | 交互式 API 文档 |
| ReDoc 文档 | http://localhost:8000/redoc | API 参考文档 |
| MinIO Console | http://localhost:9001 | 对象存储管理 |
| PostgreSQL | localhost:5432 | 数据库直连 |
| Redis | localhost:6379 | 缓存直连 |

### 默认账号

| 服务 | 用户名 | 密码 |
|------|--------|------|
| PostgreSQL | petal | petal_secret |
| MinIO | minioadmin | minioadmin |

---

## API 端点一览

| 方法 | 路径 | 说明 | 需要认证 |
|------|------|------|----------|
| GET | /health | 健康检查 | ❌ |
| POST | /api/v1/auth/wechat-login | 微信登录 | ❌ |
| POST | /api/v1/auth/refresh | 刷新 Token | ❌ |
| POST | /api/v1/anti-fake/verify | 防伪码查询 | ✅ |
| GET | /api/v1/anti-fake/history | 防伪查询历史 | ✅ |
| POST | /api/v1/anti-fake/admin/import | 批量导入防伪码 | ✅ |
| POST | /api/v1/skin/analyze | 提交肌肤分析 | ✅ |
| GET | /api/v1/skin/analyze/{id} | 查询分析结果 | ✅ |
| GET | /api/v1/skin/history | 肌肤分析历史 | ✅ |
| GET | /api/v1/skin/trend | 肌肤变化趋势 | ✅ |
| GET | /api/v1/promotions | 推广活动列表 | ❌ |
| GET | /api/v1/promotions/recommend | 个性化推荐 | ✅ |
| GET | /api/v1/promotions/{id} | 推广活动详情 | ❌ |
| POST | /api/v1/promotions/{id}/claim-coupon | 领取优惠券 | ✅ |
| POST | /api/v1/promotions/{id}/track | 行为埋点 | ✅ |
| POST | /api/v1/promotions/{id}/share | 生成分享 | ✅ |

---

## 架构说明

```
┌─────────────────┐
│   Nginx (:80)   │  ← API Gateway / 反向代理
└────────┬────────┘
         │
┌────────▼────────┐
│ FastAPI (:8000)  │  ← 4 个 Gunicorn + Uvicorn Workers
│  ├─ Auth        │
│  ├─ Anti-Fake   │
│  ├─ AI Skin     │
│  └─ Promotion   │
└─┬──────┬──────┬─┘
  │      │      │
┌─▼──┐ ┌─▼──┐ ┌─▼───┐
│ PG │ │Redis│ │MinIO│
│5432│ │6379 │ │9000 │
└────┘ └─────┘ └─────┘
```

---

## 数据库表

| 表名 | 说明 |
|------|------|
| users | 用户表（微信 openid） |
| products | 商品表 |
| anti_fake_codes | 防伪码表 |
| skin_analyses | 肌肤分析记录表 |
| promotions | 推广活动表 |
| coupons | 优惠券表 |
| promo_clicks | 推广埋点事件表 |

---

## 常见问题

### Q: 端口被占用怎么办？

修改 `deploy/docker-compose.dev.yml` 中的端口映射，例如将 80 改为 8080：
```yaml
nginx:
  ports:
    - "8080:80"
```

### Q: 如何连接数据库？

```bash
# 通过 Docker
docker exec -it deploy-postgres-1 psql -U petal -d petal

# 通过本地客户端
psql -h localhost -p 5432 -U petal -d petal
```

### Q: 如何查看后端日志？

```bash
# 实时查看
docker logs -f deploy-backend-1

# 或使用脚本
./deploy.sh logs
```

### Q: 生产环境部署注意事项

1. **修改密码**: 修改 `docker-compose.yml` 中所有默认密码
2. **JWT Secret**: 设置环境变量 `JWT_SECRET_KEY` 为强随机字符串
3. **微信配置**: 设置 `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET`
4. **SSL 证书**: 使用 `deploy/nginx.conf`（含 HTTPS）配合真实证书
5. **AI 配置**: 设置 `OPENAI_API_KEY` 或百度 AI API Key
6. **启用 Celery**: 使用 `deploy/docker-compose.yml` 启动异步任务队列
7. **数据持久化**: 确认 Docker volume 备份策略

---

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 后端框架 | FastAPI | 0.111.0 |
| ASGI 服务器 | Gunicorn + Uvicorn | 22.0.0 / 0.30.1 |
| 数据库 ORM | SQLAlchemy (Async) | 2.0.30 |
| 数据库 | PostgreSQL | 15 |
| 缓存 | Redis | 7 |
| 对象存储 | MinIO (S3 兼容) | latest |
| 反向代理 | Nginx | alpine |
| 容器化 | Docker + Docker Compose | V2 |
| 认证 | JWT (python-jose) | 3.3.0 |
| AI | OpenAI SDK | 1.30.1 |
| 测试 | pytest + pytest-asyncio | 8.2.0 |
