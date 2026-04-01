# 📐 Petal 总体架构设计

## 1. 设计原则

| 原则                 | 说明                                                         |
| -------------------- | ------------------------------------------------------------ |
| **前后端解耦**       | 前端仅通过 RESTful API 与后端通信，使用 JWT 鉴权             |
| **模块化分层**       | 后端采用 Router → Service → Repository 三层架构              |
| **可测试性**         | 依赖注入、接口抽象，方便单元/集成测试                        |
| **渐进式迭代**       | 模块间低耦合，支持独立开发、独立部署                         |
| **安全优先**         | 所有 API 经过鉴权，敏感数据加密存储，防伪码防暴力破解        |

---

## 2. 后端分层架构

```
请求 ──▶ API Router (路由 + 参数校验)
              │
              ▼
         Service Layer (业务逻辑 + 编排)
              │
              ▼
         Repository Layer (数据访问 + ORM)
              │
              ▼
         Database / Cache / External API
```

### 2.1 各层职责

| 层级         | 目录                     | 职责                                     |
| ------------ | ------------------------ | ---------------------------------------- |
| Router       | `app/api/v1/`            | 路由定义、请求参数校验、响应序列化       |
| Schema       | `app/schemas/`           | Pydantic 模型，定义请求体与响应体        |
| Service      | `app/services/`          | 核心业务逻辑，编排 Repository 和外部调用 |
| Repository   | `app/repositories/`      | 数据库 CRUD 操作，封装 ORM 细节          |
| Model        | `app/models/`            | SQLAlchemy ORM 模型定义                  |
| Core         | `app/core/`              | 配置、安全、公共依赖注入                 |

### 2.2 依赖注入模式

```python
# 示例：Service 依赖 Repository
class AntiFakeService:
    def __init__(self, repo: AntiFakeRepository = Depends(get_anti_fake_repo)):
        self.repo = repo
```

---

## 3. API 版本策略

- 所有 API 以 `/api/v1/` 为前缀
- 未来不兼容变更使用 `/api/v2/`，旧版本保留过渡期
- OpenAPI 文档自动生成：`/docs`（Swagger）、`/redoc`

---

## 4. 鉴权方案

```
微信小程序 ──wx.login()──▶ 微信服务器 ──code──▶ 后端
                                                  │
                                           code2session
                                                  │
                                            openid + session_key
                                                  │
                                           签发 JWT (access + refresh)
                                                  │
                                            返回给小程序
```

- **Access Token**: 有效期 2h，携带于 `Authorization: Bearer <token>`
- **Refresh Token**: 有效期 30d，用于无感刷新
- 后端中间件统一校验 JWT

---

## 5. 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... },
  "timestamp": 1711929600
}
```

| code | 含义                 |
| ---- | -------------------- |
| 0    | 成功                 |
| 1001 | 参数校验失败         |
| 1002 | 鉴权失败             |
| 2001 | 防伪码不存在         |
| 2002 | 防伪码已被查询过     |
| 3001 | AI 分析超时          |
| 3002 | 图片格式不支持       |
| 4001 | 商品不存在           |

---

## 6. 数据库设计概览

### 6.1 核心表

```sql
-- 用户表
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    openid        VARCHAR(64) UNIQUE NOT NULL,
    nickname      VARCHAR(128),
    avatar_url    TEXT,
    phone         VARCHAR(20),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 防伪码表
CREATE TABLE anti_fake_codes (
    id            BIGSERIAL PRIMARY KEY,
    code          VARCHAR(64) UNIQUE NOT NULL,
    product_id    BIGINT REFERENCES products(id),
    batch_no      VARCHAR(64),
    is_verified   BOOLEAN DEFAULT FALSE,
    verified_at   TIMESTAMPTZ,
    verified_by   BIGINT REFERENCES users(id),
    query_count   INT DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 产品表
CREATE TABLE products (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(256) NOT NULL,
    brand         VARCHAR(128),
    category      VARCHAR(64),
    description   TEXT,
    cover_image   TEXT,
    price         DECIMAL(10, 2),
    status        SMALLINT DEFAULT 1,   -- 1:上架 0:下架
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- AI 肌肤分析记录表
CREATE TABLE skin_analyses (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT REFERENCES users(id),
    image_url     TEXT NOT NULL,
    analysis_result JSONB,              -- AI 返回的结构化结果
    suggestions   JSONB,                -- 修复建议
    model_version VARCHAR(32),
    status        SMALLINT DEFAULT 0,   -- 0:处理中 1:完成 2:失败
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 推广活动表
CREATE TABLE promotions (
    id            BIGSERIAL PRIMARY KEY,
    title         VARCHAR(256) NOT NULL,
    description   TEXT,
    product_id    BIGINT REFERENCES products(id),
    promo_type    VARCHAR(32),          -- discount / coupon / bundle
    discount_value DECIMAL(10, 2),
    start_time    TIMESTAMPTZ,
    end_time      TIMESTAMPTZ,
    status        SMALLINT DEFAULT 1,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 推广点击/转化记录
CREATE TABLE promo_clicks (
    id            BIGSERIAL PRIMARY KEY,
    promotion_id  BIGINT REFERENCES promotions(id),
    user_id       BIGINT REFERENCES users(id),
    action        VARCHAR(32),          -- view / click / purchase
    source        VARCHAR(64),          -- scan / share / feed
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. 缓存策略

| 场景             | Key 格式                        | TTL   | 说明                     |
| ---------------- | ------------------------------- | ----- | ------------------------ |
| 防伪码查询       | `af:code:{code}`                | 24h   | 缓存查询结果，防重复查询 |
| 商品详情         | `prod:{id}`                     | 1h    | 热门商品缓存             |
| AI 分析结果      | `skin:{analysis_id}`            | 7d    | 分析结果长期缓存         |
| 用户 Session     | `session:{openid}`              | 30d   | JWT refresh token        |
| 推广活动列表     | `promo:active`                  | 10min | 活跃推广列表             |

---

## 8. 部署架构

```
                    ┌─────────────────┐
                    │   腾讯云 CDN     │
                    │  (小程序静态资源) │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    Nginx         │
                    │  (反向代理+SSL)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
     │  FastAPI App   │ │ Celery   │ │  MinIO      │
     │  (Gunicorn)    │ │ Worker   │ │  (对象存储)  │
     └────────┬──────┘ └────┬─────┘ └─────────────┘
              │              │
     ┌────────▼──────────────▼──────┐
     │     PostgreSQL  +  Redis      │
     └──────────────────────────────┘
```

---

## 9. 安全设计

1. **传输安全**: 全链路 HTTPS + TLS 1.3
2. **鉴权**: JWT + 微信 openid 绑定
3. **防伪码保护**: 
   - 查询频率限制 (同一用户 10次/分钟)
   - 查询次数记录，超过阈值标记为可疑
   - 防伪码加密存储 (SHA-256 + Salt)
4. **图片上传**: 
   - 文件类型白名单 (jpg/png/webp)
   - 文件大小限制 (≤ 10MB)
   - 内容安全审核 (调用微信内容安全 API)
5. **SQL 注入防护**: ORM 参数化查询
6. **XSS 防护**: 输入过滤 + 输出编码
