# 📢 商品推广模块 — 设计约束与实现细节

## 1. 推广类型定义

### 1.1 推广形式枚举

```python
class PromoType(str, Enum):
    DISCOUNT = "discount"       # 直接折扣 (如 7折)
    COUPON = "coupon"           # 优惠券 (满减/无门槛)
    BUNDLE = "bundle"           # 组合套装 (买一送一)
    FLASH_SALE = "flash_sale"   # 限时秒杀
    NEW_USER = "new_user"       # 新人专享
    AI_RECOMMEND = "ai_recommend"  # AI 分析推荐专属优惠
```

### 1.2 优惠券类型

```python
class CouponType(str, Enum):
    AMOUNT = "amount"           # 满减券 (满200减50)
    PERCENT = "percent"         # 折扣券 (8折)
    NO_THRESHOLD = "no_threshold"  # 无门槛券 (直减10元)
```

---

## 2. 业务规则约束

### 2.1 推广活动规则

| 规则                     | 约束值             | 说明                                        |
| ------------------------ | ------------------ | ------------------------------------------- |
| 活动标题长度             | ≤ 50 字            | 超出截断                                    |
| 活动描述长度             | ≤ 500 字           | 富文本支持                                  |
| 活动时间范围             | ≤ 90 天            | 防止永久活动                                |
| 单品同时活动数           | ≤ 3 个             | 避免优惠叠加混乱                            |
| 活动库存                 | 必填，≥ 1          | 库存为 0 自动下架                           |
| 活动状态                 | 草稿/待上架/进行中/已结束/已终止 | 状态机管理                     |

### 2.2 优惠券规则

| 规则                     | 约束值             | 说明                                        |
| ------------------------ | ------------------ | ------------------------------------------- |
| 单用户领取上限           | 1 张/活动          | 防重复领取                                  |
| 优惠券有效期             | ≤ 30 天            | 从领取时间开始计算                          |
| 满减门槛                 | ≥ 优惠金额 × 2     | 防止亏损                                    |
| 折扣范围                 | 5折 ~ 9.5折        | 合理折扣区间                                |
| 总发行量                 | 必填，有上限       | 发完即止                                    |

### 2.3 推广活动状态机

```
┌────────┐   发布    ┌──────────┐  到达开始时间  ┌──────────┐  到达结束时间  ┌──────────┐
│  DRAFT │─────────▶│ SCHEDULED│──────────────▶│  ACTIVE  │──────────────▶│  ENDED   │
│  草稿  │          │  待上架   │               │  进行中   │               │  已结束   │
└────────┘          └──────────┘               └──────────┘               └──────────┘
     │                   │                          │
     │                   │        手动终止           │
     │                   └──────────────────────────┼──────────▶┌──────────┐
     │                                              └──────────▶│ STOPPED  │
     │                                                           │ 已终止   │
     └──────────── 删除(仅草稿可删) ───▶ [DELETED]              └──────────┘
```

### 2.4 库存扣减策略

```python
"""
约束:
1. 使用 Redis 预扣库存 + 数据库最终确认 (防超卖)
2. Redis DECR 原子操作保证并发安全
3. 领券/下单后异步同步数据库库存
4. 定时任务每 5 分钟校准 Redis 与数据库库存
5. 库存降为 0 时自动更新活动状态
"""

async def claim_coupon(promo_id: int, user_id: int):
    # 1. 检查用户是否已领取
    # 2. Redis DECR 预扣库存
    # 3. 如果库存 < 0，INCR 回滚，返回已领完
    # 4. 创建优惠券记录
    # 5. 异步同步数据库库存
    ...
```

---

## 3. 推荐算法约束

### 3.1 基于 AI 分析的推荐

```python
"""
推荐策略:
1. 获取用户最近一次 AI 肌肤分析结果
2. 提取主要问题 (severity ≥ mild) 
3. 根据问题类型匹配产品标签 (问题-功效映射表)
4. 按 match_score 降序排列
5. 优先推荐有推广活动的产品
6. 最多返回 10 个推荐
"""

# 问题-功效映射表
ISSUE_PRODUCT_MAPPING = {
    "acne": ["清洁", "控油", "祛痘", "水杨酸"],
    "spot": ["美白", "淡斑", "维C", "烟酰胺"],
    "wrinkle": ["抗皱", "紧致", "视黄醇", "胶原蛋白"],
    "pore": ["收毛孔", "控油", "清洁"],
    "dark_circle": ["眼霜", "淡化黑眼圈", "咖啡因"],
    "redness": ["舒缓", "修护", "敏感肌专用"],
    "dryness": ["保湿", "补水", "透明质酸", "神经酰胺"],
    "oiliness": ["控油", "清爽", "哑光"],
    "uneven_tone": ["均匀肤色", "提亮", "美白"],
    "sagging": ["紧致", "提拉", "胶原蛋白"],
}
```

### 3.2 推荐评分计算

```
match_score = Σ(标签匹配权重 × 问题严重度权重) × 100

标签匹配权重:
- 完全匹配: 1.0
- 部分匹配: 0.6
- 品类匹配: 0.3

问题严重度权重:
- severe: 1.0
- moderate: 0.7
- mild: 0.4
```

---

## 4. 数据追踪约束

### 4.1 追踪事件定义

| 事件         | action 值    | 触发时机                     | 记录字段                     |
| ------------ | ------------ | ---------------------------- | ---------------------------- |
| 曝光         | `impression` | 推广卡片进入可视区域         | promo_id, source, timestamp  |
| 点击         | `click`      | 用户点击推广卡片             | promo_id, source, timestamp  |
| 详情浏览     | `view`       | 进入推广详情页               | promo_id, source, duration   |
| 领券         | `claim`      | 领取优惠券                   | promo_id, coupon_id          |
| 分享         | `share`      | 点击分享按钮                 | promo_id, share_channel      |
| 购买         | `purchase`   | 通过推广链接完成购买         | promo_id, order_id, amount   |

### 4.2 埋点上报约束

```
约束:
1. 曝光事件: 前端批量上报，每 10 条或 30 秒一批
2. 点击事件: 实时上报
3. 所有事件携带 source 字段标识来源
4. 事件数据先写入 Redis List，异步消费写入数据库
5. 数据保留期: 原始事件 90 天，聚合数据永久保留
6. 防重复上报: 同一用户同一推广 impression 10 分钟内去重
```

### 4.3 来源追踪 (Source)

```python
class TrackSource(str, Enum):
    HOME_BANNER = "home_banner"           # 首页轮播
    HOME_FEED = "home_feed"               # 首页信息流
    SKIN_RESULT = "skin_result_page"      # AI 分析结果页推荐
    ANTI_FAKE_RESULT = "anti_fake_result" # 防伪查询结果页推荐
    SHARE = "share"                       # 好友分享
    SEARCH = "search"                     # 搜索结果
    CATEGORY = "category"                 # 分类浏览
```

---

## 5. 后端实现约束

### 5.1 Service 层

```python
# app/services/promotion_service.py

class PromotionService:
    """
    约束:
    1. get_list() 优先从 Redis 缓存获取活跃推广列表
    2. claim_coupon() 必须保证幂等性 (同一用户同一活动只领一次)
    3. recommend() 必须关联 AI 分析结果，无分析结果时降级为热门推荐
    4. track() 异步处理，不阻塞主请求
    5. 活动状态变更通过定时任务自动管理 (Celery Beat)
    """
    
    async def get_active_promotions(self, page: int, size: int, 
                                     category: str = None) -> PagedResult:
        ...
    
    async def get_detail(self, promo_id: int) -> PromotionDetail:
        ...
    
    async def claim_coupon(self, promo_id: int, user_id: int) -> Coupon:
        ...
    
    async def get_recommendations(self, user_id: int, 
                                   analysis_id: str = None) -> List[Recommendation]:
        ...
    
    async def track_event(self, promo_id: int, user_id: int, 
                           action: str, source: str) -> None:
        ...
    
    async def generate_share(self, promo_id: int, user_id: int) -> ShareInfo:
        ...
```

### 5.2 定时任务

```python
# app/tasks/promotion_tasks.py

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # 每分钟: 检查活动状态 (上架/下架)
    sender.add_periodic_task(60.0, check_promotion_status.s())
    
    # 每5分钟: 同步 Redis 库存到数据库
    sender.add_periodic_task(300.0, sync_stock.s())
    
    # 每小时: 聚合推广数据
    sender.add_periodic_task(3600.0, aggregate_promo_analytics.s())
    
    # 每天凌晨: 过期优惠券清理
    sender.add_periodic_task(
        crontab(hour=2, minute=0), cleanup_expired_coupons.s()
    )
```

---

## 6. 前端实现约束

### 6.1 页面结构

```
miniprogram/pages/
├── promotion/
│   ├── list/              # 推广列表页
│   │   ├── index.wxml
│   │   ├── index.wxss
│   │   ├── index.js
│   │   └── index.json
│   ├── detail/            # 推广详情页
│   ├── coupon/            # 我的优惠券
│   └── recommend/         # 个性化推荐页

miniprogram/components/
├── promo-card/            # 推广卡片组件
├── coupon-card/           # 优惠券卡片组件
├── countdown/             # 倒计时组件
└── share-poster/          # 分享海报组件
```

### 6.2 交互约束

```
约束:
1. 推广列表支持下拉刷新 + 上拉加载更多
2. 推广卡片进入可视区域触发曝光埋点 (IntersectionObserver)
3. 优惠券领取按钮防抖 (500ms)
4. 领券成功后按钮变为"已领取"，不可重复点击
5. 倒计时精确到秒，客户端本地计时 + 定期同步服务端时间
6. 分享海报异步生成 + 缓存，避免重复生成
7. 推荐列表优先展示有促销的产品，无促销的灰色价格标签
```

---

## 7. 性能约束

| 指标                  | 目标值    | 说明                            |
| --------------------- | --------- | ------------------------------- |
| 推广列表加载 (P95)    | ≤ 300ms   | 缓存命中场景                    |
| 领券响应 (P95)        | ≤ 500ms   | 含 Redis 库存扣减               |
| 推荐接口 (P95)        | ≤ 800ms   | 含 AI 分析结果关联              |
| 秒杀并发领券          | ≥ 1000 QPS| Redis 原子操作保证              |
| 埋点上报延迟          | ≤ 100ms   | 异步非阻塞                      |

---

## 8. 错误处理

| 错误码 | 场景                 | 处理方式                              |
| ------ | -------------------- | ------------------------------------- |
| 4001   | 推广活动不存在       | 返回友好提示                          |
| 4002   | 推广活动未开始       | 返回开始时间，前端显示倒计时          |
| 4003   | 推广活动已结束       | 返回已结束提示                        |
| 4004   | 优惠券已领完         | 返回已领完提示                        |
| 4005   | 已领取过优惠券       | 返回已领取提示 + 优惠券信息           |
| 4006   | 优惠券已过期         | 返回过期提示                          |
| 4007   | 库存不足             | 返回库存不足提示                      |
| 4008   | 活动不可分享         | 返回提示                              |
