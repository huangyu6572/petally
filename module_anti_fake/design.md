# 🔍 防伪查询模块 — 设计约束与实现细节

## 1. 防伪码格式规范

### 1.1 编码规则

```
格式: {品牌前缀}{年月}{随机码}{校验位}
示例: PET-202604-A7X9K3M2-Q
长度: 20-32 字符
字符集: 大写字母 + 数字 (排除易混淆字符 O/0, I/1, L)
```

### 1.2 存储规范

- **原始码**: 明文存储于 `anti_fake_codes.code` 字段（用于精确匹配）
- **哈希索引**: `SHA-256(code + salt)` 存储于 `code_hash` 字段（用于安全校验）
- **Salt**: 按批次生成，存储于 `code_batches.salt`

---

## 2. 业务规则约束

### 2.1 查询规则

| 规则                     | 约束值       | 说明                                      |
| ------------------------ | ------------ | ----------------------------------------- |
| 单用户查询频率限制       | 10 次/分钟   | 基于 Redis 滑动窗口计数器                 |
| 同一 IP 查询频率限制     | 30 次/分钟   | 防止批量扫码攻击                          |
| 首次查询标记             | 写入数据库   | 记录首次查询用户和时间                    |
| 多次查询告警阈值         | ≥ 3 次       | 返回警告信息提示用户注意                  |
| 可疑码标记阈值           | ≥ 10 次      | 后台告警，人工审核                        |
| 查询结果缓存             | 24h TTL      | Redis 缓存，减轻数据库压力               |

### 2.2 防伪码状态机

```
┌──────────┐    首次查询    ┌──────────┐   查询≥3次   ┌──────────┐
│ UNUSED   │──────────────▶│ VERIFIED │─────────────▶│ WARNING  │
│ (未使用)  │               │ (已验证)  │              │ (告警)    │
└──────────┘               └──────────┘              └──────────┘
                                                          │
                                                   查询≥10次
                                                          │
                                                    ┌─────▼─────┐
                                                    │ SUSPICIOUS │
                                                    │ (可疑)      │
                                                    └───────────┘
```

### 2.3 输入校验

```python
# 防伪码格式校验正则
ANTI_FAKE_CODE_PATTERN = r'^[A-HJ-NP-Z2-9]{3}-\d{6}-[A-HJ-NP-Z2-9]{8}-[A-HJ-NP-Z2-9]$'

# 校验规则
- 长度: 20-32 字符
- 字符集: 仅允许大写字母(排除O/I/L) + 数字(排除0/1)
- 格式: 必须匹配预定义模式
- 前后空格自动裁剪
- SQL 注入字符自动过滤
```

---

## 3. 后端实现约束

### 3.1 Service 层

```python
# app/services/anti_fake_service.py

class AntiFakeService:
    """
    约束:
    1. verify_code() 必须先查 Redis 缓存，未命中再查数据库
    2. 查询成功后必须异步更新 query_count
    3. 首次查询必须记录 verified_by 和 verified_at
    4. 查询频率超限必须抛出 RateLimitExceeded 异常
    5. 所有数据库操作通过 Repository 层完成，Service 不直接操作 ORM
    """
    
    async def verify_code(self, code: str, user_id: int) -> VerifyResult:
        ...
    
    async def get_history(self, user_id: int, page: int, size: int) -> PagedResult:
        ...
    
    async def batch_import(self, file: UploadFile, operator_id: int) -> ImportResult:
        ...
```

### 3.2 Repository 层

```python
# app/repositories/anti_fake_repository.py

class AntiFakeRepository:
    """
    约束:
    1. 所有查询使用参数化查询，禁止字符串拼接
    2. 批量导入使用 bulk_insert，单次不超过 5000 条
    3. 更新 query_count 使用 F() 表达式避免竞态
    4. 查询结果必须包含关联的 product 信息 (JOIN)
    """
    
    async def find_by_code(self, code: str) -> Optional[AntiFakeCode]:
        ...
    
    async def increment_query_count(self, code_id: int) -> None:
        ...
    
    async def bulk_create(self, codes: List[AntiFakeCodeCreate]) -> int:
        ...
```

### 3.3 缓存策略

```python
# 缓存 Key 设计
CACHE_KEY_VERIFY = "af:code:{code}"          # 查询结果缓存
CACHE_KEY_RATE = "af:rate:{user_id}"          # 用户频率限制
CACHE_KEY_IP_RATE = "af:ip_rate:{ip}"         # IP 频率限制

# 缓存操作约束
- 查询命中缓存: 直接返回，但仍需异步更新 query_count
- 查询未命中: 查数据库 → 写缓存 → 返回
- 防伪码状态变更: 主动失效对应缓存
- 缓存穿透防护: 对不存在的码缓存空结果，TTL = 5min
```

---

## 4. 前端实现约束

### 4.1 扫码交互

```
约束:
1. 使用 wx.scanCode() API，支持 barCode + qrCode
2. 扫码失败时提供手动输入入口
3. 扫码结果需要前端预校验格式后再发送请求
4. 显示加载动画，超时 10s 提示重试
5. 查询结果页面支持分享（生成小程序码）
```

### 4.2 页面结构

```
miniprogram/pages/
├── anti-fake/
│   ├── scan/              # 扫码页面
│   │   ├── index.wxml
│   │   ├── index.wxss
│   │   ├── index.js
│   │   └── index.json
│   ├── result/            # 查询结果页
│   │   ├── index.wxml
│   │   ├── index.wxss
│   │   ├── index.js
│   │   └── index.json
│   └── history/           # 查询历史页
│       ├── index.wxml
│       ├── index.wxss
│       ├── index.js
│       └── index.json
```

---

## 5. 性能约束

| 指标                | 目标值    | 说明                          |
| ------------------- | --------- | ----------------------------- |
| 查询响应时间 (P95)  | ≤ 200ms   | 缓存命中场景                  |
| 查询响应时间 (P99)  | ≤ 500ms   | 缓存未命中 + 数据库查询       |
| 批量导入速度        | ≥ 1万条/s | 单次导入上限 100万条          |
| 缓存命中率          | ≥ 85%     | 热门产品防伪码                |
| 并发查询能力        | ≥ 500 QPS | 单实例，可水平扩展            |

---

## 6. 错误处理

| 错误码 | 场景             | 处理方式                           |
| ------ | ---------------- | ---------------------------------- |
| 2001   | 防伪码不存在     | 返回友好提示 + 建议检查输入        |
| 2002   | 防伪码格式错误   | 返回格式要求说明                   |
| 2003   | 查询频率超限     | 返回剩余等待时间                   |
| 2004   | 防伪码已标记可疑 | 返回风险提示 + 建议联系客服        |
| 2005   | 批量导入格式错误 | 返回错误行号和原因                 |
