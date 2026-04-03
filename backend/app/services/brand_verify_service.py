"""
Brand Official Verification Service
────────────────────────────────────
维护品牌 → 官方防伪验证地址的映射表。
当用户扫到品牌防伪码时，返回品牌官方验证 URL 供前端跳转。

设计思路：
  - 品牌防伪码数据是各品牌私有的，我们不可能也不应该自建验证
  - 正确做法：识别品牌 → 引导用户跳转品牌官方验证渠道
  - 保证数据真实性：所有验证结果来自品牌官方，我们只做跳转
"""
import json
import re
import logging
from typing import Optional, List

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# ── Redis 缓存 ────────────────────────────────────────────────────────────────
CACHE_KEY_BRANDS = "brand:verify:all"
CACHE_TTL_BRANDS = 86400    # 品牌配置缓存 24h


# ── 品牌防伪验证配置 ──────────────────────────────────────────────────────────
# 每条记录:
#   brand_key:      品牌唯一标识（小写，用于匹配）
#   brand_name:     品牌中文名
#   brand_name_en:  品牌英文名
#   code_pattern:   品牌防伪码正则（可选，用于自动识别品牌）
#   verify_type:    验证方式 — "url" / "miniprogram" / "wechat_official"
#   verify_url:     官方验证网址（verify_type=url 时使用）
#   miniprogram_id: 小程序 AppID（verify_type=miniprogram 时使用）
#   miniprogram_path: 小程序跳转路径
#   description:    验证方式说明（展示给用户）
#   logo_url:       品牌 Logo（可选）

# 内置品牌配置 —— 后续可迁移至数据库
BUILTIN_BRANDS: List[dict] = [
    {
        "brand_key": "loreal",
        "brand_name": "欧莱雅",
        "brand_name_en": "L'Oréal",
        "code_pattern": None,
        "verify_type": "miniprogram",
        "verify_url": "https://www.lorealparis.com.cn/verify",
        "miniprogram_id": "wxe8e8e8e8e8e8e8e8",  # 示例，需替换为真实 AppID
        "miniprogram_path": "/pages/verify/index",
        "description": "请使用「欧莱雅正品溯源」微信小程序扫描防伪码验证",
        "logo_url": None,
    },
    {
        "brand_key": "lancome",
        "brand_name": "兰蔻",
        "brand_name_en": "Lancôme",
        "code_pattern": None,
        "verify_type": "miniprogram",
        "verify_url": "https://www.lancome.com.cn",
        "miniprogram_id": "wxe8e8e8e8e8e8e8e8",  # 欧莱雅集团共用溯源小程序
        "miniprogram_path": "/pages/verify/index",
        "description": "兰蔻属于欧莱雅集团，请使用「欧莱雅正品溯源」小程序验证",
        "logo_url": None,
    },
    {
        "brand_key": "esteelauder",
        "brand_name": "雅诗兰黛",
        "brand_name_en": "Estée Lauder",
        "code_pattern": None,
        "verify_type": "url",
        "verify_url": "https://www.esteelauder.com.cn/verify",
        "miniprogram_id": None,
        "miniprogram_path": None,
        "description": "请前往雅诗兰黛官网输入防伪码验证",
        "logo_url": None,
    },
    {
        "brand_key": "skii",
        "brand_name": "SK-II",
        "brand_name_en": "SK-II",
        "code_pattern": None,
        "verify_type": "url",
        "verify_url": "https://www.sk-ii.com.cn/verify",
        "miniprogram_id": None,
        "miniprogram_path": None,
        "description": "请前往 SK-II 官网输入防伪码验证真伪",
        "logo_url": None,
    },
    {
        "brand_key": "florasis",
        "brand_name": "花西子",
        "brand_name_en": "Florasis",
        "code_pattern": None,
        "verify_type": "miniprogram",
        "verify_url": None,
        "miniprogram_id": "wx_florasis_example",
        "miniprogram_path": "/pages/anti-fake/index",
        "description": "请使用「花西子」微信小程序扫码验证",
        "logo_url": None,
    },
    {
        "brand_key": "perfectdiary",
        "brand_name": "完美日记",
        "brand_name_en": "Perfect Diary",
        "code_pattern": None,
        "verify_type": "miniprogram",
        "verify_url": None,
        "miniprogram_id": "wx_perfectdiary_example",
        "miniprogram_path": "/pages/verify/index",
        "description": "请使用「完美日记」微信小程序扫码验证",
        "logo_url": None,
    },
    {
        "brand_key": "shiseido",
        "brand_name": "资生堂",
        "brand_name_en": "Shiseido",
        "code_pattern": None,
        "verify_type": "url",
        "verify_url": "https://www.shiseido.com.cn/verify",
        "miniprogram_id": None,
        "miniprogram_path": None,
        "description": "请前往资生堂官网输入防伪码验证",
        "logo_url": None,
    },
    {
        "brand_key": "chanel",
        "brand_name": "香奈儿",
        "brand_name_en": "Chanel",
        "code_pattern": None,
        "verify_type": "url",
        "verify_url": "https://www.chanel.cn",
        "miniprogram_id": None,
        "miniprogram_path": None,
        "description": "请前往香奈儿官网查询产品真伪",
        "logo_url": None,
    },
    {
        "brand_key": "dior",
        "brand_name": "迪奥",
        "brand_name_en": "Dior",
        "code_pattern": None,
        "verify_type": "url",
        "verify_url": "https://www.dior.cn",
        "miniprogram_id": None,
        "miniprogram_path": None,
        "description": "请前往迪奥官网查询产品真伪",
        "logo_url": None,
    },
    {
        "brand_key": "ysl",
        "brand_name": "圣罗兰",
        "brand_name_en": "YSL",
        "code_pattern": None,
        "verify_type": "miniprogram",
        "verify_url": "https://www.yslbeauty.com.cn",
        "miniprogram_id": "wxe8e8e8e8e8e8e8e8",  # 欧莱雅集团
        "miniprogram_path": "/pages/verify/index",
        "description": "YSL 属于欧莱雅集团，请使用「欧莱雅正品溯源」小程序验证",
        "logo_url": None,
    },
]


class BrandVerifyService:
    """
    品牌防伪跳转服务。

    职责：
    1. get_all_brands()   — 返回所有支持跳转的品牌列表
    2. get_brand_info()   — 根据品牌名匹配品牌配置
    3. match_brand_by_code() — 根据防伪码格式自动识别品牌（如果有 code_pattern）
    4. get_verify_redirect() — 返回品牌官方验证跳转信息
    """

    def __init__(self, redis: Redis):
        self.redis = redis
        # 构建搜索索引（品牌名 → 配置）
        self._brand_index: dict[str, dict] = {}
        self._code_patterns: list[tuple[re.Pattern, dict]] = []
        for b in BUILTIN_BRANDS:
            # 中文名、英文名、key 都可以匹配
            self._brand_index[b["brand_key"]] = b
            self._brand_index[b["brand_name"].lower()] = b
            self._brand_index[b["brand_name_en"].lower()] = b
            if b.get("code_pattern"):
                self._code_patterns.append((re.compile(b["code_pattern"]), b))

    def get_all_brands(self) -> list[dict]:
        """返回所有支持的品牌列表（前端展示用）。"""
        return [
            {
                "brand_key": b["brand_key"],
                "brand_name": b["brand_name"],
                "brand_name_en": b["brand_name_en"],
                "verify_type": b["verify_type"],
                "description": b["description"],
                "logo_url": b.get("logo_url"),
            }
            for b in BUILTIN_BRANDS
        ]

    def get_brand_verify_info(self, brand_name: str) -> Optional[dict]:
        """
        根据品牌名查找验证跳转信息。

        返回:
        {
            "brand_name": "兰蔻",
            "brand_name_en": "Lancôme",
            "verify_type": "miniprogram",
            "verify_url": "...",
            "miniprogram_id": "wx...",
            "miniprogram_path": "/pages/verify/index",
            "description": "请使用...",
        }
        """
        key = brand_name.strip().lower()
        brand = self._brand_index.get(key)
        if brand is None:
            return None

        return {
            "brand_key": brand["brand_key"],
            "brand_name": brand["brand_name"],
            "brand_name_en": brand["brand_name_en"],
            "verify_type": brand["verify_type"],
            "verify_url": brand.get("verify_url"),
            "miniprogram_id": brand.get("miniprogram_id"),
            "miniprogram_path": brand.get("miniprogram_path"),
            "description": brand["description"],
            "logo_url": brand.get("logo_url"),
        }

    def match_brand_by_code(self, code: str) -> Optional[dict]:
        """
        尝试通过防伪码格式自动识别品牌。
        如果匹配到某个品牌的 code_pattern，返回该品牌配置；
        否则返回 None（前端需手动选择品牌）。
        """
        for pattern, brand in self._code_patterns:
            if pattern.match(code):
                return self.get_brand_verify_info(brand["brand_name"])
        return None
