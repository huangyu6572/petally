# 🌸 Petal — 微信小程序美妆平台

## 项目概述

Petal 是一套面向美妆行业的微信小程序解决方案，涵盖 **产品防伪验证**、**AI 肌肤分析** 和 **商品推广** 三大核心模块。采用前后端完全解耦架构，后端基于 Python FastAPI，前端基于微信小程序原生框架。

---

## 🏗️ 系统架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    微信小程序 (Frontend)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐      │
│  │  防伪查询模块  │  │ AI肌肤分析模块 │  │   商品推广模块    │      │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘      │
│         │                 │                    │                │
│         └─────────────────┼────────────────────┘                │
│                           │  RESTful API (HTTPS + JWT)          │
└───────────────────────────┼─────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                    API Gateway (Nginx)                           │
│                     Rate Limit / CORS / SSL                     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│               Backend (Python FastAPI)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐      │
│  │ anti_fake_svc │  │  ai_skin_svc  │  │  promotion_svc   │      │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘      │
│         │                 │                    │                │
│  ┌──────┴─────────────────┴────────────────────┴─────────┐      │
│  │              Common Layer (Auth / Cache / DB)           │      │
│  └────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                    Data Layer                                    │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   │
│   │ PostgreSQL│   │  Redis   │   │  MinIO   │   │ AI Model │   │
│   │ (主数据库) │   │ (缓存)   │   │ (对象存储)│   │ (推理服务)│   │
│   └──────────┘   └──────────┘   └──────────┘   └──────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 项目目录结构

```
Petal/
├── README.md                          # 本文件
├── docs/                              # 架构文档
│   └── architecture.md                # 总体架构设计
│
├── backend/                           # 后端服务 (Python FastAPI)
│   ├── app/
│   │   ├── main.py                    # 应用入口
│   │   ├── core/                      # 核心配置层
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── dependencies.py
│   │   ├── models/                    # 数据模型 (SQLAlchemy ORM)
│   │   ├── schemas/                   # Pydantic 请求/响应模型
│   │   ├── api/                       # 路由层
│   │   │   └── v1/
│   │   ├── services/                  # 业务逻辑层
│   │   └── repositories/             # 数据访问层
│   ├── tests/                         # 测试
│   ├── alembic/                       # 数据库迁移
│   ├── requirements.txt
│   └── Dockerfile
│
├── module_anti_fake/                  # 模块一：防伪查询
│   ├── README.md
│   ├── design.md
│   └── test_cases.md
│
├── module_ai_skin/                    # 模块二：AI 肌肤分析
│   ├── README.md
│   ├── design.md
│   └── test_cases.md
│
├── module_promotion/                  # 模块三：商品推广
│   ├── README.md
│   ├── design.md
│   └── test_cases.md
│
├── miniprogram/                       # 微信小程序前端
│   ├── app.js
│   ├── app.json
│   ├── app.wxss
│   ├── pages/
│   ├── components/
│   ├── utils/
│   └── services/
│
└── deploy/                            # 部署配置
    ├── docker-compose.yml
    ├── nginx.conf
    └── .env.example
```

---

## 🔧 技术栈

| 层级       | 技术选型                  | 说明                           |
| ---------- | ------------------------- | ------------------------------ |
| 前端       | 微信小程序原生 + Vant UI  | 轻量、兼容性好                 |
| API 网关   | Nginx                     | 反向代理、限流、SSL            |
| 后端框架   | Python 3.11 + FastAPI     | 高性能异步、自动生成 OpenAPI   |
| ORM        | SQLAlchemy 2.0 + Alembic  | 类型安全、迁移管理             |
| 数据库     | PostgreSQL 15             | 关系型主存储                   |
| 缓存       | Redis 7                   | 热点数据缓存 & 防伪码查询加速 |
| 对象存储   | MinIO / 腾讯云 COS        | 图片、AI 分析结果              |
| AI 推理    | OpenAI API / 自建模型     | 肌肤分析 & 图像识别            |
| 消息队列   | Celery + Redis             | 异步任务 (AI 分析)             |
| 容器化     | Docker + Docker Compose   | 开发/部署一致性                |
| CI/CD      | GitHub Actions            | 自动化测试、构建、部署         |

---

## 🚀 快速开始

```bash
# 1. 克隆项目
git clone <repo-url> && cd Petal

# 2. 启动后端依赖
docker-compose -f deploy/docker-compose.yml up -d

# 3. 安装后端依赖
cd backend && pip install -r requirements.txt

# 4. 数据库迁移
alembic upgrade head

# 5. 启动后端
uvicorn app.main:app --reload --port 8000

# 6. 打开微信开发者工具导入 miniprogram/ 目录
```

---

## 📖 模块文档导航

- [总体架构设计](docs/architecture.md)
- [模块一：防伪查询](module_anti_fake/README.md)
- [模块二：AI 肌肤分析](module_ai_skin/README.md)
- [模块三：商品推广](module_promotion/README.md)
