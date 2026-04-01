# 🧪 商品推广模块 — 测试用例

## 测试策略

- **单元测试**: Service / Repository / 推荐算法 (pytest)
- **集成测试**: API 端到端测试 (httpx + TestClient)
- **并发测试**: 秒杀/领券并发场景 (locust)
- **数据一致性测试**: Redis 与数据库库存一致性

---

## 1. 单元测试

### 1.1 推广活动 Service 测试

| 编号    | 用例名称                          | 前置条件                          | 操作                                           | 预期结果                                         |
| ------- | --------------------------------- | --------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| PM-U-01 | 获取活跃推广列表_正常             | 有 5 个活跃推广                   | `get_active_promotions(page=1, size=10)`       | 返回 5 条记录                                    |
| PM-U-02 | 获取活跃推广_按分类过滤           | 护肤类 3 个，彩妆类 2 个          | `get_active_promotions(category="skincare")`   | 返回 3 条记录                                    |
| PM-U-03 | 获取活跃推广_缓存命中             | Redis 有缓存                      | `get_active_promotions()`                      | 不查数据库，直接返回缓存                         |
| PM-U-04 | 获取推广详情_正常                 | 推广存在且进行中                  | `get_detail(promo_id=1)`                       | 返回完整推广详情                                 |
| PM-U-05 | 获取推广详情_不存在               | 推广不存在                        | `get_detail(promo_id=999)`                     | 抛出 `PromotionNotFound` 异常                    |

### 1.2 优惠券 Service 测试

| 编号    | 用例名称                          | 前置条件                          | 操作                                           | 预期结果                                         |
| ------- | --------------------------------- | --------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| PM-U-06 | 领取优惠券_正常                   | 活动进行中，有库存                | `claim_coupon(promo_id=1, user_id=1)`          | 返回优惠券信息，库存 -1                          |
| PM-U-07 | 领取优惠券_已领过                 | 用户已领取该活动优惠券            | `claim_coupon(promo_id=1, user_id=1)`          | 抛出 `CouponAlreadyClaimed` 异常                 |
| PM-U-08 | 领取优惠券_库存为零               | 活动库存已耗尽                    | `claim_coupon(promo_id=1, user_id=2)`          | 抛出 `CouponSoldOut` 异常                        |
| PM-U-09 | 领取优惠券_活动未开始             | 活动状态为 SCHEDULED              | `claim_coupon(promo_id=2, user_id=1)`          | 抛出 `PromotionNotStarted` 异常                  |
| PM-U-10 | 领取优惠券_活动已结束             | 活动状态为 ENDED                  | `claim_coupon(promo_id=3, user_id=1)`          | 抛出 `PromotionEnded` 异常                       |
| PM-U-11 | 领取优惠券_幂等性                 | 同一请求发送两次                  | `claim_coupon()` × 2                           | 第二次返回已领取的优惠券，不扣库存               |

### 1.3 库存管理测试

| 编号    | 用例名称                          | 操作                                           | 预期结果                                         |
| ------- | --------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| PM-U-12 | Redis 预扣库存_正常               | `decrement_stock(promo_id=1)`                  | Redis 库存 -1，返回剩余库存                      |
| PM-U-13 | Redis 预扣库存_并发安全           | 10 个协程同时 `decrement_stock()`              | 最终库存精确减少 10                              |
| PM-U-14 | Redis 库存为零_回滚               | 库存=0 时调用 `decrement_stock()`              | 返回失败，库存不变                               |
| PM-U-15 | Redis 与数据库库存同步            | `sync_stock(promo_id=1)`                       | 数据库库存与 Redis 一致                          |
| PM-U-16 | 库存降为零_自动状态变更           | 最后一张券被领取                               | 活动状态自动更新                                 |

### 1.4 推荐算法测试

| 编号    | 用例名称                          | 输入                                           | 预期结果                                         |
| ------- | --------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| PM-U-17 | 基于痘痘问题推荐                  | issues=[acne:moderate]                         | 推荐清洁/控油/祛痘产品，match_score > 80         |
| PM-U-18 | 基于多问题推荐                    | issues=[acne:moderate, dryness:mild]           | 推荐结果覆盖两类问题                             |
| PM-U-19 | 有促销活动的产品优先              | 同分产品，一个有促销一个没有                   | 有促销的排在前面                                 |
| PM-U-20 | 无 AI 分析结果_降级推荐           | analysis_id=None                               | 返回热门产品推荐                                 |
| PM-U-21 | 推荐结果不超过上限                | 大量匹配产品                                   | 最多返回 10 个推荐                               |
| PM-U-22 | match_score 计算准确              | 单标签完全匹配 + moderate 严重度               | score = 1.0 × 0.7 × 100 = 70                    |

### 1.5 数据追踪测试

| 编号    | 用例名称                          | 操作                                           | 预期结果                                         |
| ------- | --------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| PM-U-23 | 记录点击事件_正常                 | `track_event(action="click", source="feed")`   | 事件写入 Redis List                              |
| PM-U-24 | 曝光去重_10分钟内                 | 同一用户同一推广 10 分钟内发两次曝光           | 只记录一次                                       |
| PM-U-25 | 异步消费事件_写入数据库           | Redis List 有 100 条事件                       | 消费者取出并批量写入数据库                       |
| PM-U-26 | 聚合推广数据_正确计算             | 原始事件数据                                   | CTR、转化率等指标计算正确                        |

---

## 2. 集成测试 (API)

### 2.1 正常流程

| 编号    | 用例名称                          | 请求                                                        | 预期响应                                          |
| ------- | --------------------------------- | ----------------------------------------------------------- | ------------------------------------------------- |
| PM-I-01 | 获取推广列表_200                  | `GET /api/v1/promotions?page=1&size=20`                     | 200, 返回推广列表                                 |
| PM-I-02 | 获取推广详情_200                  | `GET /api/v1/promotions/1`                                  | 200, 返回推广详情                                 |
| PM-I-03 | 领取优惠券_200                    | `POST /api/v1/promotions/1/claim-coupon`                    | 200, 返回优惠券信息                               |
| PM-I-04 | 个性化推荐_200                    | `GET /api/v1/promotions/recommend?analysis_id=ana_xxx`      | 200, 返回推荐列表                                 |
| PM-I-05 | 记录推广行为_200                  | `POST /api/v1/promotions/1/track {"action":"click"}`        | 200                                               |
| PM-I-06 | 生成分享信息_200                  | `POST /api/v1/promotions/1/share`                           | 200, 返回小程序码 URL + 分享文案                  |
| PM-I-07 | 完整用户旅程                      | 浏览列表 → 详情 → 领券 → 分享                              | 全流程成功，埋点数据完整                          |

### 2.2 异常流程

| 编号    | 用例名称                          | 请求                                                        | 预期响应                                          |
| ------- | --------------------------------- | ----------------------------------------------------------- | ------------------------------------------------- |
| PM-I-08 | 推广不存在_404                    | `GET /api/v1/promotions/99999`                              | 404 或 200 + `code=4001`                          |
| PM-I-09 | 活动未开始_业务错误               | 领取未开始活动的优惠券                                      | 200, `code=4002`, 含开始时间                      |
| PM-I-10 | 活动已结束_业务错误               | 领取已结束活动的优惠券                                      | 200, `code=4003`                                  |
| PM-I-11 | 优惠券已领完_业务错误             | 库存为 0 时领券                                              | 200, `code=4004`                                  |
| PM-I-12 | 重复领券_业务错误                 | 同一用户再次领同一活动券                                     | 200, `code=4005`, 返回已领的券信息                |
| PM-I-13 | 未登录_401                        | 不携带 Token                                                | 401                                               |

---

## 3. 并发测试

### 3.1 秒杀场景

```python
# locustfile.py 伪代码
class FlashSaleUser(HttpUser):
    wait_time = constant(0)  # 无等待，模拟瞬间并发
    
    @task
    def claim_coupon(self):
        """秒杀领券"""
        self.client.post(f"/api/v1/promotions/{FLASH_SALE_ID}/claim-coupon",
                         headers={"Authorization": f"Bearer {self.token}"})
```

### 3.2 并发测试用例

| 编号    | 用例名称                          | 场景                                           | 预期结果                                         |
| ------- | --------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| PM-C-01 | 秒杀_100人抢50张券                | 100 个用户同时请求                             | 恰好 50 人成功，50 人收到已领完提示              |
| PM-C-02 | 秒杀_不超卖                       | 库存 100，200 并发请求                         | 成功数 ≤ 100，数据库和 Redis 库存一致            |
| PM-C-03 | 秒杀_Redis 与 DB 最终一致         | 高并发领券后触发同步                           | Redis 库存 = 数据库库存                          |
| PM-C-04 | 同一用户并发领券_幂等             | 同一用户同一时刻发 5 次请求                    | 只成功 1 次，库存只减 1                          |

### 3.3 并发测试指标

| 场景                   | 并发用户 | 目标 QPS | P95 延迟 | 错误率 | 超卖率 |
| ---------------------- | -------- | -------- | -------- | ------ | ------ |
| 秒杀领券               | 1000     | ≥ 500    | ≤ 1s     | ≤ 1%   | 0%     |
| 正常领券               | 200      | ≥ 200    | ≤ 500ms  | ≤ 0.5% | 0%     |
| 推广列表浏览           | 500      | ≥ 1000   | ≤ 300ms  | ≤ 0.1% | N/A    |

---

## 4. 数据一致性测试

| 编号    | 用例名称                          | 测试方式                                       | 预期结果                                         |
| ------- | --------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| PM-D-01 | 领券后库存一致                    | 领券成功 → 检查 Redis + DB 库存               | 两者一致                                         |
| PM-D-02 | 库存同步任务正确                  | 手动修改 Redis 库存 → 触发同步                 | DB 库存更新为 Redis 值                           |
| PM-D-03 | 过期券自动清理                    | 创建过期优惠券 → 触发清理任务                  | 过期券状态更新为 EXPIRED                         |
| PM-D-04 | 活动自动上架                      | 创建 SCHEDULED 活动，到达开始时间              | 状态自动变为 ACTIVE                              |
| PM-D-05 | 活动自动下架                      | 进行中活动到达结束时间                         | 状态自动变为 ENDED                               |
| PM-D-06 | 埋点数据完整性                    | 完整用户旅程后检查事件数据                     | 所有事件都已记录，无丢失                         |

---

## 5. 安全测试

| 编号    | 用例名称                          | 攻击方式                                       | 预期防护                                         |
| ------- | --------------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| PM-S-01 | 伪造优惠券ID                      | 修改请求中的 coupon_id                         | 服务端校验 coupon 归属，拒绝非本人券             |
| PM-S-02 | 绕过库存限制                      | 并发请求试图超领                               | Redis 原子操作保证不超卖                         |
| PM-S-03 | 刷推广数据                        | 批量伪造 track 事件                            | 频率限制 + 去重 + 异常检测                       |
| PM-S-04 | 修改推广价格                      | 篡改请求中的价格字段                           | 价格从服务端获取，不信任前端                     |
| PM-S-05 | 越权访问管理端                    | 普通用户 Token 调用 admin 接口                 | 返回 403                                        |
| PM-S-06 | 分享链接注入                      | 分享链接中注入恶意参数                         | 参数白名单校验                                   |

---

## 6. 测试 Fixtures

```python
# tests/fixtures/promotion.py

import pytest
from datetime import datetime, timedelta

@pytest.fixture
def seed_promotions(db_session, seed_products):
    """预置推广活动数据"""
    now = datetime.utcnow()
    promotions = [
        # 进行中的活动
        Promotion(
            id=1, title="春季护肤节", product_id=seed_products[0].id,
            promo_type="discount", discount_value=0.7,
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=14),
            status=PromotionStatus.ACTIVE, stock=100
        ),
        # 未开始的活动
        Promotion(
            id=2, title="夏日防晒季", product_id=seed_products[1].id,
            promo_type="coupon", discount_value=50.0,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=60),
            status=PromotionStatus.SCHEDULED, stock=500
        ),
        # 已结束的活动
        Promotion(
            id=3, title="冬季保湿节", product_id=seed_products[0].id,
            promo_type="bundle",
            start_time=now - timedelta(days=60),
            end_time=now - timedelta(days=30),
            status=PromotionStatus.ENDED, stock=0
        ),
    ]
    db_session.add_all(promotions)
    db_session.commit()
    return promotions

@pytest.fixture
def seed_coupons(db_session, seed_promotions, seed_users):
    """预置优惠券数据"""
    coupons = [
        Coupon(
            id="cpn_001", promotion_id=1, user_id=seed_users[0].id,
            discount_type="percent", discount_value=0.7,
            min_purchase=200.0,
            valid_until=datetime.utcnow() + timedelta(days=30),
            status="unused"
        ),
    ]
    db_session.add_all(coupons)
    db_session.commit()
    return coupons

@pytest.fixture
def redis_stock(redis_client, seed_promotions):
    """初始化 Redis 库存"""
    for promo in seed_promotions:
        redis_client.set(f"promo:stock:{promo.id}", promo.stock)
```
