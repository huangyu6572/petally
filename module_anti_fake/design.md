# 🔍 防伪查询模块 — 设计文档

## 1. 模块概述

防伪查询模块提供两条独立查询路径，不依赖任何自建防伪码体系：

| 路径 | 输入 | 实现 | 结果 |
|------|------|------|------|
| **条形码备案查询** | 商品条形码（EAN-8/EAN-13/UPC-A） | Open Beauty Facts API + Redis 缓存 | 返回产品信息 |
| **品牌官方验证** | 品牌名称 | 本地品牌配置表 | 跳转至品牌官网或官方小程序 |

---

## 2. 接口设计

### 2.1 接口列表

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET`  | `/api/v1/anti-fake/brands`       | ✅ JWT | 获取支持品牌列表 |
| `POST` | `/api/v1/anti-fake/barcode`      | ✅ JWT | 条形码备案查询 |
| `POST` | `/api/v1/anti-fake/brand-verify` | ✅ JWT | 品牌官方跳转 |
| `GET`  | `/api/v1/anti-fake/history`      | ✅ JWT | 用户查询历史 |

### 2.2 条形码查询

**请求**
```json
POST /api/v1/anti-fake/barcode
{ "barcode": "3600523541875" }
```

**格式约束**：8–14 位纯数字（EAN-8 / EAN-13 / UPC-A / UPC-E）

**响应（产品存在）**
```json
{
  "code": 0,
  "data": {
    "found": true,
    "barcode": "3600523541875",
    "source": "open_beauty_facts",
    "product": {
      "product_name": "Rénergie Multi-Lift",
      "brands": "Lancôme",
      "categories": "Skincare",
      "image_url": "https://images.openbeautyfacts.org/...",
      "ingredients_text": "Aqua, ..."
    }
  }
}
```

**响应（产品不存在）**
```json
{ "code": 0, "data": { "found": false, "barcode": "1234567890123" } }
```

### 2.3 品牌官方跳转

**请求**
```json
POST /api/v1/anti-fake/brand-verify
{ "brand_name": "兰蔻" }
```

**响应（URL 跳转型）**
```json
{
  "code": 0,
  "data": {
    "brand_name": "兰蔻",
    "verify_type": "url",
    "verify_url": "https://www.lancome.com.cn/authenticity",
    "miniprogram_id": null,
    "instruction": "点击跳转至兰蔻官方防伪验证页面"
  }
}
```

**响应（小程序跳转型）**
```json
{
  "code": 0,
  "data": {
    "brand_name": "花西子",
    "verify_type": "miniprogram",
    "verify_url": null,
    "miniprogram_id": "wx_florasis_official",
    "instruction": "点击跳转至花西子官方小程序验证"
  }
}
```

---

## 3. 支持品牌列表（10 个）

| 品牌 | verify_type | 目标 |
|------|-------------|------|
| 欧莱雅 | url | loreal.com.cn |
| 兰蔻  | url | lancome.com.cn |
| 雅诗兰黛 | url | esteelauder.com.cn |
| SK-II | url | sk-ii.com.cn |
| 花西子 | miniprogram | wx_florasis_official |
| 完美日记 | miniprogram | wx_perfectdiary_official |
| 资生堂 | url | shiseido.com.cn |
| 香奈儿 | url | chanel.com |
| 迪奥   | url | dior.com |
| YSL   | url | ysl.com |

---

## 4. 数据流

### 条形码查询流程

```
小程序扫码
    │
    ▼
POST /anti-fake/barcode
    │
    ▼
OpenBeautyService.lookup_barcode(barcode)
    │
    ├─ Redis HIT (obf:barcode:{barcode}, TTL 7d) ──→ 直接返回缓存
    │
    └─ Redis MISS
           │
           ▼
       GET https://world.openbeautyfacts.org/api/v2/product/{barcode}.json
           │
           ├─ 200 + status=1 → 解析产品信息 → 缓存 7 天 → 返回 found=true
           └─ 404 / 未找到   → 写入哨兵 "__MISS__" → 缓存 1 小时 → 返回 found=false
    │
    ▼
_save_history() → 写入 verify_history 表（query_type="barcode"）
    │
    ▼
返回响应
```

### 品牌跳转流程

```
用户点击品牌验证
    │
    ▼
POST /anti-fake/brand-verify
    │
    ▼
BrandVerifyService.get_brand_verify_info(brand_name)
    │
    ├─ verify_type=url         → 返回 verify_url（客户端 wx.navigateTo webview）
    └─ verify_type=miniprogram → 返回 miniprogram_id（客户端 wx.navigateToMiniProgram）
    │
    ▼
_save_history() → 写入 verify_history 表（query_type="brand_redirect"）
    │
    ▼
返回响应
```

---

## 5. 缓存策略

| 场景 | Redis Key | TTL |
|------|-----------|-----|
| OBF 查询命中 | `obf:barcode:{barcode}` | 7 天 |
| OBF 查询未找到 | `obf:barcode:{barcode}` = `"__MISS__"` | 1 小时 |

---

## 6. 数据库模型

### `verify_history` 表

```sql
CREATE TABLE verify_history (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id),
    query_type   VARCHAR(32) NOT NULL,     -- 'barcode' | 'brand_redirect'
    query_value  VARCHAR(128) NOT NULL,    -- 条形码 or 品牌名
    product_name VARCHAR(256),             -- 查到的产品名（条形码查询时）
    brand_name   VARCHAR(128),
    result_summary VARCHAR(256),
    created_at   TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ix_verify_history_user_created ON verify_history (user_id, created_at);
```

---

## 7. 错误码

| code | HTTP | 说明 |
|------|------|------|
| `422` | 422 | 条形码格式非法（非 8–14 位数字） |
| `3001` | 404 | 品牌不存在（不在支持列表中） |
| `3002` | 502 | Open Beauty Facts API 不可用 |

---

## 8. 服务层文件

| 文件 | 说明 |
|------|------|
| `app/services/open_beauty_service.py` | OBF API 客户端 + Redis 缓存 |
| `app/services/brand_verify_service.py` | 品牌配置表 + 查找逻辑 |
| `app/api/v1/endpoints/anti_fake.py` | 路由 + 历史记录写入 |
| `app/schemas/anti_fake.py` | Pydantic 请求/响应 Schema |
| `app/models/models.py` | `VerifyHistory` ORM 模型 |

---

## 9. 前端页面结构

```
miniprogram/pages/anti-fake/
├── scan/      # 扫码页：扫条形码 + 品牌选择
│   ├── index.js   — 扫码逻辑、品牌 overlay 选择
│   ├── index.wxml — 双入口 UI + 品牌列表 overlay
│   └── index.wxss
├── result/    # 结果页：条形码查询结果 / 品牌跳转确认
│   ├── index.js   — 根据 type=barcode/brand 分支渲染
│   ├── index.wxml — 两套 UI 布局
│   └── index.wxss
└── history/   # 历史页：条形码 + 品牌跳转记录
    ├── index.js
    ├── index.wxml
    └── index.wxss
```
