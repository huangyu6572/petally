# 🤖 AI 肌肤分析模块 — 设计约束与实现细节

## 1. AI 服务架构

### 1.1 推理管线 (Pipeline)

```
原始图片 ──▶ 预处理 ──▶ 人脸检测 ──▶ 区域分割 ──▶ 问题检测 ──▶ 评分 ──▶ 建议生成
                │           │            │            │          │          │
                ▼           ▼            ▼            ▼          ▼          ▼
             裁剪/缩放   MediaPipe   语义分割    多标签分类   规则引擎    LLM API
             质量校验    /MTCNN      U-Net       ResNet/ViT   权重评分   GPT/文心
```

### 1.2 AI 接口抽象

```python
# app/services/ai/base.py

from abc import ABC, abstractmethod

class SkinAnalyzerBase(ABC):
    """
    AI 分析器抽象基类
    约束: 所有 AI 实现必须继承此类，便于切换不同的 AI 供应商
    """
    
    @abstractmethod
    async def detect_issues(self, image_url: str) -> List[SkinIssue]:
        """检测肌肤问题"""
        ...
    
    @abstractmethod
    async def generate_suggestions(self, issues: List[SkinIssue], skin_type: str) -> List[Suggestion]:
        """生成修复建议"""
        ...
    
    @abstractmethod
    async def get_overall_score(self, issues: List[SkinIssue]) -> int:
        """计算综合评分 (0-100)"""
        ...
```

### 1.3 AI 供应商适配

```python
# 支持的 AI 供应商 (策略模式，运行时可切换)

class OpenAISkinAnalyzer(SkinAnalyzerBase):
    """OpenAI GPT-4 Vision 实现"""
    ...

class BaiduSkinAnalyzer(SkinAnalyzerBase):
    """百度 AI 人脸分析实现"""
    ...

class LocalModelSkinAnalyzer(SkinAnalyzerBase):
    """本地模型实现 (PyTorch / ONNX)"""
    ...

# 工厂方法
def get_skin_analyzer(provider: str = None) -> SkinAnalyzerBase:
    provider = provider or settings.AI_PROVIDER
    analyzers = {
        "openai": OpenAISkinAnalyzer,
        "baidu": BaiduSkinAnalyzer,
        "local": LocalModelSkinAnalyzer,
    }
    return analyzers[provider]()
```

---

## 2. 业务规则约束

### 2.1 图片处理规则

| 规则                 | 约束值         | 说明                                    |
| -------------------- | -------------- | --------------------------------------- |
| 支持格式             | jpg/png/webp   | 其他格式返回 3002 错误                  |
| 最大文件大小         | 10 MB          | 超限返回 413                            |
| 最小分辨率           | 480 × 480 px   | 低于最小分辨率影响分析精度              |
| 最大分辨率           | 4096 × 4096 px | 超出自动缩放                            |
| 图片预处理           | 统一缩放至 1024×1024 | 送入模型前标准化                    |
| 人脸检测             | 至少检测到 1 张人脸 | 未检测到返回 3003 错误              |
| 内容安全审核         | 调用微信 API   | 不合规内容拒绝并记录                    |

### 2.2 分析类型定义

| 类型          | 枚举值       | 检测范围                         | 适用场景             |
| ------------- | ------------ | -------------------------------- | -------------------- |
| 全脸分析      | `face_full`  | 全脸所有问题                     | 日常肌肤自测         |
| 肌肤特写      | `skin_close` | 局部皮肤纹理分析                 | 关注特定区域         |
| 痘痘聚焦      | `acne_focus` | 专注痤疮/粉刺检测                | 痘痘困扰用户         |

### 2.3 肌肤问题分类

```python
class SkinIssueType(str, Enum):
    ACNE = "acne"                    # 痘痘/粉刺
    SPOT = "spot"                    # 色斑/雀斑
    WRINKLE = "wrinkle"              # 皱纹/细纹
    PORE = "pore"                    # 毛孔粗大
    DARK_CIRCLE = "dark_circle"      # 黑眼圈
    REDNESS = "redness"              # 泛红/敏感
    DRYNESS = "dryness"              # 干燥/脱皮
    OILINESS = "oiliness"           # 出油/油光
    UNEVEN_TONE = "uneven_tone"      # 肤色不均
    SAGGING = "sagging"              # 松弛/下垂

class Severity(str, Enum):
    NONE = "none"          # 无问题 (score >= 80)
    MILD = "mild"          # 轻微 (score 60-79)
    MODERATE = "moderate"  # 中度 (score 40-59)
    SEVERE = "severe"      # 严重 (score < 40)
```

### 2.4 评分体系

```
综合评分 = Σ(各问题评分 × 权重) / Σ(权重)

权重表:
- 痘痘/粉刺: 0.20
- 色斑: 0.15
- 皱纹: 0.15
- 毛孔: 0.10
- 黑眼圈: 0.10
- 泛红: 0.10
- 干燥: 0.05
- 出油: 0.05
- 肤色不均: 0.05
- 松弛: 0.05

单项评分: 0-100 (100 = 完美, 0 = 最严重)
综合评分: 0-100
```

---

## 3. 后端实现约束

### 3.1 异步任务处理

```python
# app/services/skin_analysis_service.py

class SkinAnalysisService:
    """
    约束:
    1. analyze() 必须是异步的，立即返回 analysis_id，后台 Celery 处理
    2. 分析超时上限: 60 秒，超时标记为 FAILED
    3. 失败自动重试: 最多 3 次，指数退避 (2s, 4s, 8s)
    4. 图片必须先上传到对象存储，AI 服务通过 URL 访问
    5. 分析结果写入数据库后，主动失效相关缓存
    6. 每个用户每天限制分析 20 次 (防滥用)
    """
    
    async def submit_analysis(self, user_id: int, image: UploadFile, 
                               analysis_type: str) -> str:
        """提交分析任务，返回 analysis_id"""
        # 1. 校验图片格式和大小
        # 2. 内容安全审核
        # 3. 上传到对象存储
        # 4. 创建数据库记录 (status=PROCESSING)
        # 5. 发送 Celery 任务
        # 6. 返回 analysis_id
        ...
    
    async def get_result(self, analysis_id: str, user_id: int) -> SkinAnalysisResult:
        """获取分析结果"""
        ...
    
    async def get_trend(self, user_id: int, days: int) -> TrendResult:
        """获取肌肤变化趋势"""
        ...
```

### 3.2 Celery 任务定义

```python
# app/tasks/skin_tasks.py

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=2,
    soft_time_limit=55,
    time_limit=60,
)
def process_skin_analysis(self, analysis_id: str):
    """
    约束:
    1. 软超时 55s 时保存中间结果
    2. 硬超时 60s 时标记为 TIMEOUT
    3. 异常自动重试，重试间隔指数退避
    4. 成功后通过 WebSocket 或写入状态表通知前端
    """
    try:
        analyzer = get_skin_analyzer()
        # 1. 从对象存储获取图片
        # 2. 执行 AI 分析
        # 3. 计算评分
        # 4. 生成建议
        # 5. 匹配推荐产品
        # 6. 写入数据库
        # 7. 更新缓存
    except SoftTimeLimitExceeded:
        # 保存中间结果，标记为 TIMEOUT
        ...
    except Exception as exc:
        self.retry(exc=exc, countdown=2 ** self.request.retries)
```

### 3.3 图片存储约束

```
对象存储路径规范:
bucket: petal-skin-images
path: /{year}/{month}/{day}/{user_id}/{analysis_id}.{ext}
示例: /2026/04/01/10001/ana_20260401_abc123.jpg

约束:
- 图片保留期: 90 天 (可配置)
- 到期自动清理 (对象存储生命周期策略)
- 访问权限: 签名 URL，有效期 1 小时
- 原始图片和处理后图片分别存储
```

---

## 4. Prompt Engineering 约束 (LLM 建议生成)

### 4.1 系统 Prompt

```
你是一位专业的皮肤科顾问，根据 AI 肌肤检测结果，为用户提供个性化的护肤建议。

要求:
1. 使用通俗易懂的语言，避免过度专业术语
2. 建议分为 "护肤方案" 和 "生活习惯" 两大类
3. 每条建议控制在 50 字以内
4. 不做医疗诊断，严重问题建议就医
5. 推荐产品时说明匹配原因
6. 语气温和友好，给予积极鼓励
```

### 4.2 输入格式

```json
{
  "skin_type": "混合偏油",
  "issues": [
    {"type": "acne", "severity": "moderate", "score": 35},
    {"type": "pore", "severity": "mild", "score": 65}
  ],
  "user_age_range": "20-25",
  "season": "春季"
}
```

### 4.3 输出格式约束

```json
{
  "suggestions": [
    {
      "category": "skincare | lifestyle",
      "title": "≤10字标题",
      "content": "≤50字建议内容",
      "priority": 1
    }
  ]
}
```

---

## 5. 前端实现约束

### 5.1 拍照/上传交互

```
约束:
1. 使用 wx.chooseMedia() 选择图片，支持拍照和相册
2. 前端压缩: 宽度 > 2048px 时等比缩放
3. 上传进度显示
4. 分析等待页面: 显示预计时间 + 动画
5. 结果轮询间隔: 2 秒，最多轮询 30 次 (60秒)
6. 分析结果可视化: 在图片上标注问题区域
7. 建议列表支持展开/收起
```

### 5.2 页面结构

```
miniprogram/pages/
├── skin/
│   ├── capture/           # 拍照/上传页面
│   │   ├── index.wxml
│   │   ├── index.wxss
│   │   ├── index.js
│   │   └── index.json
│   ├── analyzing/         # 分析等待页面
│   ├── result/            # 分析结果页
│   ├── history/           # 历史记录页
│   └── trend/             # 趋势图表页
```

---

## 6. 性能约束

| 指标                | 目标值    | 说明                          |
| ------------------- | --------- | ----------------------------- |
| 图片上传时间        | ≤ 3s      | 压缩后 ≤ 2MB                 |
| AI 分析时间 (P95)   | ≤ 15s     | 含所有 pipeline 步骤          |
| AI 分析时间 (P99)   | ≤ 30s     | 复杂图片或排队场景            |
| 结果页加载时间      | ≤ 1s      | 缓存命中                      |
| 并发分析能力        | ≥ 50/min  | Celery worker 可水平扩展      |
| 日分析量上限        | 10万次    | 与 AI API 配额对齐            |

---

## 7. 错误处理

| 错误码 | 场景                | 处理方式                              |
| ------ | ------------------- | ------------------------------------- |
| 3001   | AI 分析超时         | 提示用户稍后查看，保留重试入口        |
| 3002   | 图片格式不支持      | 提示支持的格式列表                    |
| 3003   | 未检测到人脸        | 提示拍照指导（光线、角度、距离）      |
| 3004   | 图片内容违规        | 提示内容不合规                        |
| 3005   | 日分析次数超限      | 提示剩余次数和重置时间                |
| 3006   | AI 服务不可用       | 降级提示，建议稍后重试                |
| 3007   | 图片质量过低        | 提示重新拍摄，给出拍照建议            |
