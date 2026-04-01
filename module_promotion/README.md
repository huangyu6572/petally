# 📢 模块三：商品推广

## 模块概述

为美妆品牌和商家提供商品推广能力，支持多种推广形式（优惠券、限时折扣、组合套装等），结合 AI 肌肤分析结果进行精准推荐，并提供完整的推广效果追踪和数据分析。

---

## 核心功能

| 功能               | 说明                                                   |
| ------------------ | ------------------------------------------------------ |
| 推广活动管理       | 创建/编辑/上下架推广活动                               |
| 商品展示           | 推广商品详情页，含图片、描述、价格                     |
| 优惠券系统         | 优惠券的发放、领取、核销                               |
| 精准推荐           | 基于 AI 肌肤分析结果推荐适合的产品                     |
| 分享裂变           | 小程序码分享、邀请好友得优惠                           |
| 数据追踪           | 曝光、点击、转化等数据统计                             |
| 内容种草           | 商品关联使用心得/测评内容                               |

---

## API 设计

### 1. 获取推广活动列表

```
GET /api/v1/promotions?page=1&size=20&category=skincare
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "total": 35,
    "items": [
      {
        "id": 1,
        "title": "春季护肤节 — 精华水买一送一",
        "description": "花瓣精华水限时活动",
        "promo_type": "bundle",
        "product": {
          "id": 1001,
          "name": "花瓣精华水",
          "cover_image": "https://cdn.example.com/products/1001.jpg",
          "original_price": 299.00,
          "promo_price": 299.00,
          "tag": "买一送一"
        },
        "start_time": "2026-04-01T00:00:00Z",
        "end_time": "2026-04-15T23:59:59Z",
        "remaining_stock": 500
      }
    ]
  }
}
```

### 2. 获取推广详情

```
GET /api/v1/promotions/{promotion_id}
```

### 3. 领取优惠券

```
POST /api/v1/promotions/{promotion_id}/claim-coupon
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "coupon_id": "cpn_20260401_abc",
    "discount_type": "amount",
    "discount_value": 50.00,
    "min_purchase": 200.00,
    "valid_until": "2026-04-30T23:59:59Z",
    "status": "unused"
  }
}
```

### 4. 个性化推荐 (基于 AI 分析)

```
GET /api/v1/promotions/recommend?analysis_id=ana_20260401_abc123
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "based_on": {
      "skin_type": "混合偏油",
      "main_issues": ["acne", "pore"]
    },
    "recommendations": [
      {
        "product_id": 1001,
        "name": "花瓣氨基酸洁面乳",
        "match_reason": "温和清洁，适合中度痘痘肌肤",
        "match_score": 95,
        "promotion": {
          "id": 5,
          "promo_price": 89.00,
          "original_price": 129.00,
          "tag": "7折"
        }
      },
      {
        "product_id": 1002,
        "name": "花瓣控油精华",
        "match_reason": "控油收毛孔，改善 T 区出油",
        "match_score": 88,
        "promotion": null
      }
    ]
  }
}
```

### 5. 记录推广行为

```
POST /api/v1/promotions/{promotion_id}/track
```

**Request:**
```json
{
  "action": "click",
  "source": "skin_result_page"
}
```

### 6. 分享推广 (生成小程序码)

```
POST /api/v1/promotions/{promotion_id}/share
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "share_url": "pages/promotion/detail/index?id=1&ref=u10001",
    "qrcode_url": "https://cdn.example.com/qrcodes/promo_1_u10001.png",
    "share_title": "花瓣精华水买一送一，快来看看！",
    "share_image": "https://cdn.example.com/shares/promo_1.jpg"
  }
}
```

### 7. 推广数据看板 (管理端)

```
GET /api/v1/admin/promotions/{promotion_id}/analytics
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "promotion_id": 1,
    "period": "2026-04-01 ~ 2026-04-07",
    "metrics": {
      "impressions": 15000,
      "clicks": 3200,
      "ctr": 0.213,
      "coupon_claimed": 800,
      "coupon_used": 320,
      "conversions": 280,
      "conversion_rate": 0.0875,
      "revenue": 83720.00,
      "share_count": 450,
      "share_conversions": 85
    },
    "daily_trend": [
      {"date": "2026-04-01", "impressions": 2100, "clicks": 450, "conversions": 40}
    ],
    "top_sources": [
      {"source": "skin_result_page", "clicks": 1500, "conversion_rate": 0.12},
      {"source": "home_banner", "clicks": 800, "conversion_rate": 0.08},
      {"source": "share", "clicks": 450, "conversion_rate": 0.19}
    ]
  }
}
```

---

## 用户流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                      用户触达渠道                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ 首页推荐  │  │ AI分析   │  │ 好友分享  │  │ 防伪查询后推荐  │   │
│  │ 轮播/信息流│  │ 结果页推荐│  │ 小程序码  │  │                 │   │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └────────┬─────────┘   │
│        │             │             │                 │              │
│        └─────────────┼─────────────┼─────────────────┘              │
│                      │    (记录曝光来源)                              │
│                      ▼                                               │
│              ┌───────────────┐                                       │
│              │  推广详情页    │                                       │
│              │  - 商品信息    │                                       │
│              │  - 优惠信息    │                                       │
│              │  - 领券入口    │                                       │
│              └───────┬───────┘                                       │
│                      │ (记录点击)                                     │
│           ┌──────────┼──────────┐                                    │
│           ▼          ▼          ▼                                    │
│    ┌──────────┐ ┌─────────┐ ┌──────────┐                           │
│    │  领取优惠 │ │ 立即购买 │ │ 分享好友  │                           │
│    │  券      │ │ (跳转)  │ │ (裂变)   │                           │
│    └──────────┘ └─────────┘ └──────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
```
