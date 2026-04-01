# 🧪 防伪查询模块 — 测试用例

## 测试策略

- **单元测试**: Service / Repository 层逻辑 (pytest + pytest-asyncio)
- **集成测试**: API 端到端测试 (httpx + TestClient)
- **性能测试**: 并发查询压测 (locust)
- **安全测试**: 注入/越权/暴力破解

---

## 1. 单元测试

### 1.1 Service 层测试

| 编号    | 用例名称                         | 前置条件                          | 操作                                    | 预期结果                                              |
| ------- | -------------------------------- | --------------------------------- | --------------------------------------- | ----------------------------------------------------- |
| AF-U-01 | 查询有效防伪码_首次              | 防伪码存在且未被查询过            | `verify_code("PET-202604-A7X9K3M2-Q")` | 返回 `is_authentic=True, first_verified=True`         |
| AF-U-02 | 查询有效防伪码_非首次            | 防伪码已被查询 2 次               | `verify_code("PET-202604-A7X9K3M2-Q")` | 返回 `is_authentic=True, query_count=3`               |
| AF-U-03 | 查询有效防伪码_触发告警          | 防伪码已被查询 9 次               | `verify_code("PET-202604-A7X9K3M2-Q")` | 返回 `warning` 字段，query_count=10                   |
| AF-U-04 | 查询不存在的防伪码               | 防伪码不在数据库中                | `verify_code("INVALID-CODE")`           | 抛出 `AntiFakeCodeNotFound` 异常                      |
| AF-U-05 | 查询格式非法的防伪码             | 输入含特殊字符                    | `verify_code("'; DROP TABLE--")`        | 抛出 `InvalidCodeFormat` 异常                         |
| AF-U-06 | 查询命中缓存                     | Redis 中有对应缓存                | `verify_code("PET-202604-A7X9K3M2-Q")` | 不查数据库，直接返回缓存结果                          |
| AF-U-07 | 查询频率超限                     | 用户 1 分钟内已查询 10 次          | `verify_code("ANY-CODE")`               | 抛出 `RateLimitExceeded` 异常                         |
| AF-U-08 | 缓存穿透防护                     | 查询不存在的码                    | 连续查询同一个不存在的码                | 第二次命中空缓存，不再查数据库                        |

### 1.2 Repository 层测试

| 编号    | 用例名称                         | 操作                                     | 预期结果                                      |
| ------- | -------------------------------- | ---------------------------------------- | --------------------------------------------- |
| AF-U-09 | 按防伪码查询_存在                | `find_by_code("PET-202604-A7X9K3M2-Q")` | 返回 AntiFakeCode 对象，含关联 Product        |
| AF-U-10 | 按防伪码查询_不存在              | `find_by_code("NOT-EXIST")`              | 返回 `None`                                   |
| AF-U-11 | 更新查询计数_并发安全            | 10 个协程同时 `increment_query_count(1)` | `query_count` 最终精确增加 10                 |
| AF-U-12 | 批量导入_正常                    | `bulk_create(5000条有效数据)`            | 返回成功数量 5000                             |
| AF-U-13 | 批量导入_部分重复                | `bulk_create(含3条已存在的码)`           | 抛出异常或返回去重后的成功数量                |
| AF-U-14 | 批量导入_超过单次上限            | `bulk_create(6000条)`                    | 抛出 `BatchSizeExceeded` 异常                 |

---

## 2. 集成测试 (API)

### 2.1 正常流程

| 编号    | 用例名称                         | 请求                                                           | 预期响应                                             |
| ------- | -------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------- |
| AF-I-01 | 查询有效防伪码_首次_200          | `POST /api/v1/anti-fake/verify {"code":"PET-202604-A7X9K3M2-Q"}` | 200, `code=0`, `is_authentic=true`, `first_verified=true` |
| AF-I-02 | 查询有效防伪码_非首次_200        | 再次发送同一请求                                                | 200, `code=0`, `first_verified=false`, `query_count=2`   |
| AF-I-03 | 查询历史_200                     | `GET /api/v1/anti-fake/history?page=1&size=20`                 | 200, 返回历史列表，包含 AF-I-01 的记录                    |
| AF-I-04 | 查询历史_分页_200                | `GET /api/v1/anti-fake/history?page=2&size=2`                  | 200, 正确分页                                             |

### 2.2 异常流程

| 编号    | 用例名称                         | 请求                                                           | 预期响应                                     |
| ------- | -------------------------------- | -------------------------------------------------------------- | -------------------------------------------- |
| AF-I-05 | 防伪码不存在_业务错误            | `POST /api/v1/anti-fake/verify {"code":"NOT-EXIST-CODE"}`     | 200, `code=2001`                             |
| AF-I-06 | 防伪码格式错误_400               | `POST /api/v1/anti-fake/verify {"code":"ab"}`                  | 422, 参数校验失败                            |
| AF-I-07 | 缺少 code 字段_400               | `POST /api/v1/anti-fake/verify {}`                             | 422, 缺少必填字段                            |
| AF-I-08 | 未登录查询_401                   | 不携带 Authorization header                                    | 401, `code=1002`                             |
| AF-I-09 | 频率超限_429                     | 1 分钟内发送 11 次请求                                          | 429, `code=2003`, 含剩余等待时间             |

---

## 3. 性能测试

### 3.1 压测场景

```python
# locustfile.py 伪代码
class AntiFakeUser(HttpUser):
    wait_time = between(0.1, 0.5)
    
    @task(8)
    def verify_existing_code(self):
        """查询存在的防伪码 (模拟缓存命中场景)"""
        self.client.post("/api/v1/anti-fake/verify", 
                         json={"code": random.choice(EXISTING_CODES)})
    
    @task(2)
    def verify_random_code(self):
        """查询随机码 (模拟缓存未命中)"""
        self.client.post("/api/v1/anti-fake/verify",
                         json={"code": generate_random_code()})
```

### 3.2 性能指标

| 场景                   | 并发用户 | 目标 QPS | P95 延迟 | P99 延迟 | 错误率 |
| ---------------------- | -------- | -------- | -------- | -------- | ------ |
| 查询_缓存命中          | 100      | ≥ 500    | ≤ 200ms  | ≤ 500ms  | ≤ 0.1% |
| 查询_缓存未命中        | 100      | ≥ 200    | ≤ 500ms  | ≤ 1000ms | ≤ 0.5% |
| 混合场景 (8:2)         | 200      | ≥ 400    | ≤ 300ms  | ≤ 800ms  | ≤ 0.2% |

---

## 4. 安全测试

| 编号    | 用例名称                         | 攻击方式                                      | 预期防护                                     |
| ------- | -------------------------------- | --------------------------------------------- | -------------------------------------------- |
| AF-S-01 | SQL 注入测试                     | `code: "'; DROP TABLE anti_fake_codes; --"`   | 参数化查询阻断，返回格式错误                 |
| AF-S-02 | XSS 注入测试                     | `code: "<script>alert(1)</script>"`           | 输入过滤，返回格式错误                       |
| AF-S-03 | 暴力破解防伪码                   | 循环尝试不同码 (>30次/分钟)                   | IP 限流触发，返回 429                        |
| AF-S-04 | 越权查询他人历史                 | 篡改 user_id 参数                             | JWT 中提取 user_id，忽略请求参数             |
| AF-S-05 | 非管理员调用批量导入             | 普通用户 Token 调用 admin 接口                | 返回 403                                     |

---

## 5. 测试数据准备

```python
# tests/fixtures/anti_fake.py

import pytest

@pytest.fixture
def seed_anti_fake_codes(db_session):
    """预置测试防伪码数据"""
    codes = [
        AntiFakeCode(code="PET-202604-A7X9K3M2-Q", product_id=1, is_verified=False, query_count=0),
        AntiFakeCode(code="PET-202604-B8Y0L4N3-R", product_id=1, is_verified=True, query_count=2),
        AntiFakeCode(code="PET-202604-C9Z1M5P4-S", product_id=2, is_verified=True, query_count=9),
    ]
    db_session.add_all(codes)
    db_session.commit()
    return codes

@pytest.fixture
def seed_products(db_session):
    """预置测试产品数据"""
    products = [
        Product(id=1, name="花瓣精华水", brand="Petal", category="护肤", price=299.00),
        Product(id=2, name="花瓣面膜", brand="Petal", category="面膜", price=199.00),
    ]
    db_session.add_all(products)
    db_session.commit()
    return products
```
