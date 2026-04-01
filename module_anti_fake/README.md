# 🔍 模块一：美妆产品防伪查询

## 模块概述

用户通过扫描产品防伪码或手动输入，查询美妆产品的真伪信息。系统返回产品详情、生产批次、认证状态等，帮助用户辨别正品。

---

## 核心功能

| 功能           | 说明                                           |
| -------------- | ---------------------------------------------- |
| 防伪码扫描     | 支持扫描条形码/二维码，自动提取防伪码          |
| 手动输入查询   | 用户手动输入防伪码进行查询                     |
| 查询结果展示   | 展示产品信息、认证状态、历史查询次数           |
| 查询历史       | 用户可查看自己的历史查询记录                   |
| 防伪码管理     | 后台批量导入/生成防伪码（管理端）              |

---

## API 设计

### 1. 查询防伪码

```
POST /api/v1/anti-fake/verify
```

**Request Body:**
```json
{
  "code": "PET20260401ABC123"
}
```

**Response (正品):**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_authentic": true,
    "product": {
      "id": 1001,
      "name": "花瓣精华水",
      "brand": "Petal",
      "category": "护肤",
      "cover_image": "https://cdn.example.com/products/1001.jpg",
      "batch_no": "B20260301",
      "production_date": "2026-03-01",
      "expiry_date": "2029-03-01"
    },
    "verification": {
      "first_verified": true,
      "query_count": 1,
      "verified_at": "2026-04-01T10:00:00Z"
    }
  }
}
```

**Response (非首次查询):**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "is_authentic": true,
    "product": { ... },
    "verification": {
      "first_verified": false,
      "query_count": 3,
      "first_verified_at": "2026-03-15T08:30:00Z",
      "warning": "该防伪码已被查询过 3 次，请注意辨别"
    }
  }
}
```

**Response (无效码):**
```json
{
  "code": 2001,
  "message": "防伪码不存在，请确认输入是否正确",
  "data": null
}
```

### 2. 查询历史记录

```
GET /api/v1/anti-fake/history?page=1&size=20
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "total": 5,
    "items": [
      {
        "code": "PET20260401ABC123",
        "product_name": "花瓣精华水",
        "is_authentic": true,
        "queried_at": "2026-04-01T10:00:00Z"
      }
    ]
  }
}
```

### 3. 批量导入防伪码（管理端）

```
POST /api/v1/admin/anti-fake/import
Content-Type: multipart/form-data
```

---

## 用户流程

```
┌─────────────┐     ┌───────────────┐     ┌──────────────┐
│  用户扫描/   │────▶│  前端发送请求  │────▶│  后端验证     │
│  手动输入码  │     │  POST /verify  │     │  anti_fake   │
└─────────────┘     └───────────────┘     └──────┬───────┘
                                                  │
                                    ┌─────────────┼──────────────┐
                                    │             │              │
                              ┌─────▼────┐  ┌────▼─────┐  ┌────▼─────┐
                              │ Redis缓存 │  │ 数据库   │  │ 记录日志 │
                              │ 命中?     │  │ 查询     │  │ 更新计数 │
                              └──────────┘  └──────────┘  └──────────┘
                                    │
                              ┌─────▼────────────┐
                              │  返回查询结果     │
                              │  (含风险提示)     │
                              └──────────────────┘
```
