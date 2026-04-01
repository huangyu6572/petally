# 🤖 模块二：AI 肌肤分析

## 模块概述

用户上传人脸照片或皮肤局部照片，系统调用 AI 接口进行肌肤分析，识别当前肌肤问题（如痘痘、色斑、皱纹、毛孔粗大等），并给出个性化的修复建议和产品推荐。

---

## 核心功能

| 功能               | 说明                                                 |
| ------------------ | ---------------------------------------------------- |
| 拍照/上传照片      | 支持实时拍照或从相册选择                             |
| AI 肌肤检测        | 识别多种肌肤问题，输出结构化分析结果                 |
| 问题描述           | 对每个检测到的问题给出通俗易懂的描述                 |
| 修复建议           | 针对问题给出护肤方案和生活习惯建议                   |
| 产品推荐           | 基于分析结果推荐合适的美妆/护肤产品                  |
| 历史记录           | 保存分析历史，支持对比查看肌肤变化趋势               |
| 分析报告分享       | 生成可分享的肌肤分析报告海报                         |

---

## API 设计

### 1. 提交肌肤分析

```
POST /api/v1/skin/analyze
Content-Type: multipart/form-data
```

**Request:**
- `image`: 图片文件 (jpg/png/webp, ≤ 10MB)
- `analysis_type`: 分析类型 (`face_full` | `skin_close` | `acne_focus`)

**Response (异步任务已创建):**
```json
{
  "code": 0,
  "message": "分析任务已提交",
  "data": {
    "analysis_id": "ana_20260401_abc123",
    "status": "processing",
    "estimated_seconds": 15
  }
}
```

### 2. 查询分析结果

```
GET /api/v1/skin/analyze/{analysis_id}
```

**Response (分析完成):**
```json
{
  "code": 0,
  "data": {
    "analysis_id": "ana_20260401_abc123",
    "status": "completed",
    "overall_score": 72,
    "skin_type": "混合偏油",
    "issues": [
      {
        "type": "acne",
        "severity": "moderate",
        "score": 35,
        "label": "痘痘/粉刺",
        "description": "面部 T 区检测到中度痤疮，主要集中在额头和鼻翼两侧",
        "regions": [
          {"x": 120, "y": 80, "w": 40, "h": 40, "confidence": 0.92}
        ]
      },
      {
        "type": "pore",
        "severity": "mild",
        "score": 65,
        "label": "毛孔粗大",
        "description": "鼻部及脸颊区域毛孔略显粗大"
      },
      {
        "type": "dark_circle",
        "severity": "mild",
        "score": 58,
        "label": "黑眼圈",
        "description": "眼下区域有轻微色素沉着"
      }
    ],
    "suggestions": [
      {
        "category": "skincare",
        "title": "日常清洁",
        "content": "建议使用氨基酸洁面乳，每天早晚各一次，避免过度清洁"
      },
      {
        "category": "skincare",
        "title": "控油保湿",
        "content": "T区使用控油精华，两颊使用保湿乳液，维持水油平衡"
      },
      {
        "category": "lifestyle",
        "title": "饮食建议",
        "content": "减少高糖高油食物摄入，多吃富含维生素C的水果蔬菜"
      },
      {
        "category": "lifestyle",
        "title": "作息建议",
        "content": "保证每天 7-8 小时睡眠，避免熬夜"
      }
    ],
    "recommended_products": [
      {
        "product_id": 1001,
        "name": "花瓣氨基酸洁面乳",
        "match_reason": "温和清洁，适合混合偏油肌肤",
        "match_score": 95
      }
    ],
    "created_at": "2026-04-01T10:00:00Z",
    "model_version": "skin-v2.1"
  }
}
```

### 3. 获取分析历史

```
GET /api/v1/skin/history?page=1&size=10
```

### 4. 获取肌肤趋势

```
GET /api/v1/skin/trend?days=90
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "overall_scores": [
      {"date": "2026-01-15", "score": 62},
      {"date": "2026-02-10", "score": 68},
      {"date": "2026-03-20", "score": 72}
    ],
    "improvement": "+16%",
    "best_improved": "acne",
    "needs_attention": "dark_circle"
  }
}
```

---

## 用户流程

```
┌─────────────┐     ┌───────────────┐     ┌──────────────────┐
│  用户拍照/   │────▶│  图片预处理    │────▶│  上传至对象存储   │
│  选择照片    │     │  (裁剪/压缩)   │     │  (MinIO/COS)     │
└─────────────┘     └───────────────┘     └────────┬─────────┘
                                                    │
                                          ┌─────────▼──────────┐
                                          │  创建分析任务       │
                                          │  返回 analysis_id   │
                                          └─────────┬──────────┘
                                                    │
                                          ┌─────────▼──────────┐
                                          │  Celery 异步任务    │
                                          │  调用 AI 推理服务   │
                                          └─────────┬──────────┘
                                                    │
                                    ┌───────────────┼───────────────┐
                                    │               │               │
                              ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
                              │ 肌肤检测  │  │ 问题分析  │  │ 建议生成  │
                              │ (CV模型)  │  │ (规则引擎)│  │ (LLM)    │
                              └───────────┘  └───────────┘  └───────────┘
                                    │
                              ┌─────▼──────────────┐
                              │  写入分析结果       │
                              │  通知前端 (WebSocket│
                              │  或轮询)            │
                              └────────────────────┘
```
