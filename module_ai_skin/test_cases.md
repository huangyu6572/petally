# 🧪 AI 肌肤分析模块 — 测试用例

## 测试策略

- **单元测试**: Service / AI Adapter 层逻辑 (pytest + mock)
- **集成测试**: API 端到端测试，含图片上传 (httpx + TestClient)
- **AI 准确性测试**: 标注数据集验证 (人工标注 + 自动对比)
- **性能测试**: 并发上传/分析压测 (locust)
- **安全测试**: 恶意文件上传、内容安全

---

## 1. 单元测试

### 1.1 图片预处理测试

| 编号    | 用例名称                         | 输入                             | 预期结果                                      |
| ------- | -------------------------------- | -------------------------------- | --------------------------------------------- |
| SK-U-01 | 有效JPG图片_正常处理             | 1024×768 JPG, 2MB               | 成功预处理，输出 1024×1024                    |
| SK-U-02 | 有效PNG图片_正常处理             | 800×600 PNG, 1MB                | 成功预处理                                    |
| SK-U-03 | 超大图片_自动缩放               | 4096×3072 JPG, 8MB              | 自动缩放至 1024×1024                          |
| SK-U-04 | 低分辨率图片_拒绝               | 320×240 JPG                     | 抛出 `ImageResolutionTooLow` 异常             |
| SK-U-05 | 不支持格式_拒绝                  | BMP 文件                         | 抛出 `UnsupportedImageFormat` 异常            |
| SK-U-06 | 超大文件_拒绝                    | 15MB JPG                         | 抛出 `FileSizeTooLarge` 异常                  |
| SK-U-07 | 伪装图片_拒绝                    | 将 EXE 改名为 .jpg               | 通过 magic bytes 检测，拒绝                   |

### 1.2 AI 分析器测试 (Mock)

| 编号    | 用例名称                         | Mock 行为                        | 预期结果                                      |
| ------- | -------------------------------- | -------------------------------- | --------------------------------------------- |
| SK-U-08 | 正常分析_返回问题列表            | AI 返回 3 个问题                 | Service 正确解析，生成 SkinAnalysisResult      |
| SK-U-09 | AI 返回空问题列表                | AI 返回 0 个问题                 | 综合评分 = 100，无建议                        |
| SK-U-10 | AI 超时_自动重试                 | 第1次超时，第2次成功             | Celery 重试后成功完成                         |
| SK-U-11 | AI 连续失败_标记失败             | 连续 3 次失败                    | 分析记录标记为 FAILED                         |
| SK-U-12 | AI 返回格式异常_容错处理         | AI 返回非预期 JSON               | 降级处理，记录错误日志                        |

### 1.3 评分计算测试

| 编号    | 用例名称                         | 输入                                      | 预期结果                            |
| ------- | -------------------------------- | ----------------------------------------- | ----------------------------------- |
| SK-U-13 | 综合评分_全部满分                | 所有问题 score=100                        | overall_score = 100                 |
| SK-U-14 | 综合评分_混合分数                | acne=35, pore=65, dark_circle=58          | overall_score = 加权计算结果        |
| SK-U-15 | 综合评分_全部最低                | 所有问题 score=0                          | overall_score = 0                   |
| SK-U-16 | 严重度判定_none                  | score=85                                  | severity = "none"                   |
| SK-U-17 | 严重度判定_mild                  | score=65                                  | severity = "mild"                   |
| SK-U-18 | 严重度判定_moderate              | score=45                                  | severity = "moderate"               |
| SK-U-19 | 严重度判定_severe                | score=30                                  | severity = "severe"                 |

### 1.4 建议生成测试

| 编号    | 用例名称                         | 输入                                      | 预期结果                                  |
| ------- | -------------------------------- | ----------------------------------------- | ----------------------------------------- |
| SK-U-20 | 痘痘问题_生成护肤建议           | issues=[acne:moderate]                    | 建议中包含清洁和控油相关内容              |
| SK-U-21 | 多问题_建议去重排序             | issues=[acne, pore, oiliness]             | 建议不重复，按优先级排序                  |
| SK-U-22 | 严重问题_建议就医               | issues=[acne:severe]                      | 建议中包含就医建议                        |
| SK-U-23 | 产品推荐_匹配问题类型           | issues=[dryness:moderate]                 | 推荐保湿类产品，match_score ≥ 80          |

### 1.5 Service 层测试

| 编号    | 用例名称                         | 操作                                      | 预期结果                                  |
| ------- | -------------------------------- | ----------------------------------------- | ----------------------------------------- |
| SK-U-24 | 提交分析_正常                    | `submit_analysis(user, image, "face_full")` | 返回 analysis_id, 状态=PROCESSING        |
| SK-U-25 | 日次数超限                       | 用户已分析 20 次后再次提交                | 抛出 `DailyLimitExceeded` 异常            |
| SK-U-26 | 查询结果_存在且完成              | `get_result("ana_xxx", user_id)`          | 返回完整分析结果                          |
| SK-U-27 | 查询结果_处理中                  | `get_result("ana_xxx", user_id)`          | 返回 status=PROCESSING                   |
| SK-U-28 | 查询结果_不存在                  | `get_result("not_exist", user_id)`        | 抛出 `AnalysisNotFound` 异常              |
| SK-U-29 | 查询他人结果_拒绝                | `get_result("ana_xxx", other_user_id)`    | 抛出 `PermissionDenied` 异常              |

---

## 2. 集成测试 (API)

### 2.1 正常流程

| 编号    | 用例名称                         | 请求                                                   | 预期响应                                          |
| ------- | -------------------------------- | ------------------------------------------------------ | ------------------------------------------------- |
| SK-I-01 | 提交分析_有效图片_200            | `POST /api/v1/skin/analyze` + JPG 文件                 | 200, `code=0`, 返回 analysis_id, status=processing |
| SK-I-02 | 查询结果_分析完成_200            | `GET /api/v1/skin/analyze/{id}` (等待完成后)           | 200, 返回完整分析结果                              |
| SK-I-03 | 查询历史_200                     | `GET /api/v1/skin/history?page=1&size=10`              | 200, 返回历史列表                                  |
| SK-I-04 | 查询趋势_200                     | `GET /api/v1/skin/trend?days=90`                       | 200, 返回趋势数据                                  |
| SK-I-05 | 完整流程_提交到获取结果          | 提交 → 轮询 → 获取结果                                | 全流程成功，≤ 30s 完成                             |

### 2.2 异常流程

| 编号    | 用例名称                         | 请求                                                   | 预期响应                                          |
| ------- | -------------------------------- | ------------------------------------------------------ | ------------------------------------------------- |
| SK-I-06 | 不支持格式_422                   | `POST /analyze` + BMP 文件                              | 422 或 200 + `code=3002`                          |
| SK-I-07 | 文件过大_413                     | `POST /analyze` + 15MB JPG                              | 413                                                |
| SK-I-08 | 无人脸_业务错误                  | `POST /analyze` + 风景照                                | 200, `code=3003`                                  |
| SK-I-09 | 未登录_401                       | 不携带 Token                                            | 401                                                |
| SK-I-10 | 查询不存在的分析_404             | `GET /analyze/not_exist_id`                             | 404                                                |
| SK-I-11 | 日次数超限_429                   | 第 21 次提交                                            | 429, `code=3005`                                  |

---

## 3. AI 准确性测试

### 3.1 测试数据集

```
tests/fixtures/skin_dataset/
├── acne/
│   ├── mild/          # 30 张轻度痘痘
│   ├── moderate/      # 30 张中度痘痘
│   └── severe/        # 30 张重度痘痘
├── spot/              # 色斑样本
├── wrinkle/           # 皱纹样本
├── pore/              # 毛孔样本
├── clean/             # 无问题样本
└── labels.json        # 人工标注标签
```

### 3.2 准确性指标

| 指标       | 目标值 | 说明                                   |
| ---------- | ------ | -------------------------------------- |
| 检测召回率 | ≥ 85%  | 不漏检重要问题                         |
| 检测精确率 | ≥ 80%  | 减少误报                               |
| 严重度准确 | ≥ 75%  | severe/moderate/mild 分级准确          |
| 肤质判断   | ≥ 80%  | 油性/干性/混合/敏感 判断准确           |

### 3.3 准确性测试用例

| 编号    | 用例名称                         | 输入                      | 预期结果                              |
| ------- | -------------------------------- | ------------------------- | ------------------------------------- |
| SK-A-01 | 明显痘痘_正确检出                | 中度痘痘样本              | 检出 acne, severity=moderate          |
| SK-A-02 | 无问题肌肤_无误报               | 健康肌肤样本              | 所有问题 severity=none                |
| SK-A-03 | 多问题并存_全部检出              | 痘痘+色斑+毛孔样本       | 3 个问题全部检出                      |
| SK-A-04 | 不同光线_鲁棒性                  | 同一人不同光线下的照片    | 分析结果差异 ≤ 15%                    |
| SK-A-05 | 不同角度_鲁棒性                  | 同一人不同角度照片        | 分析结果差异 ≤ 20%                    |

---

## 4. 性能测试

### 4.1 压测场景

```python
# locustfile.py 伪代码
class SkinAnalysisUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def submit_and_poll(self):
        """提交分析 + 轮询结果"""
        # 1. 上传图片
        resp = self.client.post("/api/v1/skin/analyze", files={"image": sample_image})
        analysis_id = resp.json()["data"]["analysis_id"]
        
        # 2. 轮询结果 (最多 15 次，间隔 2s)
        for _ in range(15):
            resp = self.client.get(f"/api/v1/skin/analyze/{analysis_id}")
            if resp.json()["data"]["status"] == "completed":
                break
            time.sleep(2)
```

### 4.2 性能指标

| 场景                   | 并发用户 | 目标吞吐 | P95 延迟   | 错误率 |
| ---------------------- | -------- | -------- | ---------- | ------ |
| 图片上传               | 50       | ≥ 30/s   | ≤ 3s       | ≤ 0.5% |
| AI 分析完成            | 50       | ≥ 3/min  | ≤ 15s      | ≤ 2%   |
| 结果查询 (缓存命中)   | 100      | ≥ 200/s  | ≤ 300ms    | ≤ 0.1% |

---

## 5. 安全测试

| 编号    | 用例名称                         | 攻击方式                                    | 预期防护                                  |
| ------- | -------------------------------- | ------------------------------------------- | ----------------------------------------- |
| SK-S-01 | 恶意文件上传                     | 上传含恶意代码的图片                        | magic bytes 检测拦截                      |
| SK-S-02 | 超大文件 DoS                     | 连续上传 10MB+ 文件                         | 文件大小限制 + 上传频率限制               |
| SK-S-03 | 路径遍历                         | filename 含 `../../etc/passwd`              | 文件名清洗，只允许安全字符                |
| SK-S-04 | 违规内容上传                     | 上传不合规图片                              | 内容安全 API 拦截，记录并封禁             |
| SK-S-05 | 越权查看他人分析结果             | 修改 URL 中的 analysis_id                    | JWT 绑定 user_id 校验                     |
| SK-S-06 | AI Prompt 注入                   | 图片中嵌入文字指令                          | AI 输入过滤 + 输出格式校验                |

---

## 6. 测试 Fixtures

```python
# tests/fixtures/skin_analysis.py

import pytest
from PIL import Image
from io import BytesIO

@pytest.fixture
def sample_face_image():
    """生成模拟人脸图片 (用于测试预处理)"""
    img = Image.new('RGB', (1024, 768), color='beige')
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    buffer.seek(0)
    return buffer

@pytest.fixture
def mock_ai_response():
    """模拟 AI 分析响应"""
    return {
        "issues": [
            {"type": "acne", "severity": "moderate", "score": 35,
             "regions": [{"x": 120, "y": 80, "w": 40, "h": 40, "confidence": 0.92}]},
            {"type": "pore", "severity": "mild", "score": 65, "regions": []},
        ],
        "skin_type": "combination_oily",
        "model_version": "skin-v2.1"
    }

@pytest.fixture
def seed_skin_analyses(db_session, seed_users):
    """预置分析记录"""
    analyses = [
        SkinAnalysis(
            id="ana_20260401_001", user_id=seed_users[0].id,
            image_url="https://storage.example.com/skin/test.jpg",
            status=1,  # COMPLETED
            analysis_result={"overall_score": 72, "issues": [...]},
            suggestions=[...],
            model_version="skin-v2.1"
        ),
        SkinAnalysis(
            id="ana_20260401_002", user_id=seed_users[0].id,
            image_url="https://storage.example.com/skin/test2.jpg",
            status=0,  # PROCESSING
        ),
    ]
    db_session.add_all(analyses)
    db_session.commit()
    return analyses
```
