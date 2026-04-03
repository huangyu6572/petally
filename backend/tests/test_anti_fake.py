"""
Anti-Fake Module v2 — 完整测试套件
涵盖:
  F1 - 条形码查询（OpenBeautyService: 缓存命中/未命中/OBF 无数据/OBF 超时/脏数据）
  F2 - 品牌防伪跳转（BrandVerifyService: 品牌列表/中英文匹配/key 匹配/code_pattern）
  F3 - BarcodeRequest Schema 校验（合法/非法条形码）
  F4 - BrandVerifyRequest Schema 校验
  F5 - API 端点集成测试（/barcode, /brand-verify, /brands, /history）
"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.open_beauty_service import (
    OpenBeautyService,
    OBF_API_BASE,
    CACHE_KEY_BARCODE,
    CACHE_TTL_HIT,
    CACHE_TTL_MISS,
)
from app.services.brand_verify_service import (
    BrandVerifyService,
    BUILTIN_BRANDS,
)
from app.schemas.anti_fake import (
    BarcodeRequest,
    BrandVerifyRequest,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

SAMPLE_OBF_RESPONSE = {
    "status": 1,
    "product": {
        "code": "3337875597371",
        "product_name": "CeraVe Moisturizing Cream",
        "brands": "CeraVe",
        "categories": "Moisturizers",
        "image_url": "https://images.openfoodfacts.org/images/products/333/787/559/7371/front_fr.8.400.jpg",
        "ingredients_text": "Aqua, Glycerin, Cetearyl Alcohol",
        "labels": "Dermatologist Tested",
        "quantity": "50ml",
        "packaging": "Tube",
    },
}

SAMPLE_OBF_NOT_FOUND = {"status": 0, "status_verbose": "product not found"}

SAMPLE_OBF_NO_NAME = {
    "status": 1,
    "product": {
        "code": "0000000000001",
        "product_name": "",
        "brands": "Unknown",
    },
}

SAMPLE_BARCODE = "3337875597371"
SAMPLE_MISSING_BARCODE = "9999999999999"


def make_redis_mock():
    redis = AsyncMock()
    redis.get.return_value = None
    redis.setex.return_value = True
    return redis


def make_obf_service(redis=None):
    if redis is None:
        redis = make_redis_mock()
    return OpenBeautyService(redis=redis)


def make_brand_service(redis=None):
    if redis is None:
        redis = make_redis_mock()
    return BrandVerifyService(redis=redis)


# ══════════════════════════════════════════════════════════════════════════════
# F1 — OpenBeautyService 条形码查询
# ══════════════════════════════════════════════════════════════════════════════

class TestOpenBeautyServiceCacheHit:
    """OBF-CACHE: Redis 缓存命中测试"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_product(self):
        """OBF-CACHE-01: 缓存中有产品数据 → 直接返回，不调用 OBF API"""
        redis = make_redis_mock()
        cached_product = {
            "barcode": SAMPLE_BARCODE,
            "product_name": "CeraVe Moisturizing Cream",
            "brand": "CeraVe",
            "category": "Moisturizers",
            "source": "Open Beauty Facts",
        }
        redis.get.return_value = json.dumps(cached_product)

        svc = make_obf_service(redis)
        result = await svc.lookup_barcode(SAMPLE_BARCODE)

        assert result is not None
        assert result["product_name"] == "CeraVe Moisturizing Cream"
        assert result["brand"] == "CeraVe"
        # 不应再调用 setex（缓存已存在）
        redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_sentinel_returns_none(self):
        """OBF-CACHE-02: 缓存中存在 __MISS__ 哨兵值 → 返回 None"""
        redis = make_redis_mock()
        redis.get.return_value = '"__MISS__"'

        svc = make_obf_service(redis)
        result = await svc.lookup_barcode(SAMPLE_MISSING_BARCODE)

        assert result is None
        redis.setex.assert_not_called()


class TestOpenBeautyServiceApiFetch:
    """OBF-API: OBF API 调用测试"""

    @pytest.mark.asyncio
    async def test_api_success_returns_product(self):
        """OBF-API-01: OBF 返回产品数据 → 解析并缓存"""
        redis = make_redis_mock()
        svc = make_obf_service(redis)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_OBF_RESPONSE

        with patch("app.services.open_beauty_service.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            result = await svc.lookup_barcode(SAMPLE_BARCODE)

        assert result is not None
        assert result["barcode"] == SAMPLE_BARCODE
        assert result["product_name"] == "CeraVe Moisturizing Cream"
        assert result["brand"] == "CeraVe"
        assert result["category"] == "Moisturizers"
        assert result["ingredients"] == "Aqua, Glycerin, Cetearyl Alcohol"
        assert result["labels"] == "Dermatologist Tested"
        assert result["quantity"] == "50ml"
        assert result["source"] == "Open Beauty Facts"
        assert SAMPLE_BARCODE in result["source_url"]

        # 验证写入了 HIT 缓存
        redis.setex.assert_called_once()
        call_args = redis.setex.call_args
        assert SAMPLE_BARCODE in str(call_args)
        assert call_args[0][1] == CACHE_TTL_HIT

    @pytest.mark.asyncio
    async def test_api_product_not_found(self):
        """OBF-API-02: OBF 返回 status=0 → 返回 None，写 MISS 缓存"""
        redis = make_redis_mock()
        svc = make_obf_service(redis)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_OBF_NOT_FOUND

        with patch("app.services.open_beauty_service.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            result = await svc.lookup_barcode(SAMPLE_MISSING_BARCODE)

        assert result is None
        # 验证写入了 MISS 缓存
        redis.setex.assert_called_once()
        call_args = redis.setex.call_args
        assert call_args[0][1] == CACHE_TTL_MISS
        assert "__MISS__" in str(call_args)

    @pytest.mark.asyncio
    async def test_api_product_empty_name_treated_as_not_found(self):
        """OBF-API-03: 产品名为空的脏数据 → 视为未找到"""
        redis = make_redis_mock()
        svc = make_obf_service(redis)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_OBF_NO_NAME

        with patch("app.services.open_beauty_service.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            result = await svc.lookup_barcode("0000000000001")

        assert result is None

    @pytest.mark.asyncio
    async def test_api_http_error_returns_none(self):
        """OBF-API-04: OBF 返回非 200 → 返回 None"""
        redis = make_redis_mock()
        svc = make_obf_service(redis)

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("app.services.open_beauty_service.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            result = await svc.lookup_barcode(SAMPLE_BARCODE)

        assert result is None

    @pytest.mark.asyncio
    async def test_api_timeout_returns_none(self):
        """OBF-API-05: OBF API 超时 → 返回 None"""
        redis = make_redis_mock()
        svc = make_obf_service(redis)

        with patch("app.services.open_beauty_service.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = httpx.TimeoutException("timeout")
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            result = await svc.lookup_barcode(SAMPLE_BARCODE)

        assert result is None

    @pytest.mark.asyncio
    async def test_api_brand_missing_defaults_to_unknown(self):
        """OBF-API-06: 品牌字段缺失 → 默认为 '未知品牌'"""
        redis = make_redis_mock()
        svc = make_obf_service(redis)

        obf_data = {
            "status": 1,
            "product": {
                "code": "1234567890123",
                "product_name": "Mystery Cream",
                "brands": "",
                "categories": "",
            },
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = obf_data

        with patch("app.services.open_beauty_service.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            result = await svc.lookup_barcode("1234567890123")

        assert result is not None
        assert result["brand"] == "未知品牌"
        assert result["category"] == "化妆品"


# ══════════════════════════════════════════════════════════════════════════════
# F2 — BrandVerifyService 品牌防伪跳转
# ══════════════════════════════════════════════════════════════════════════════

class TestBrandVerifyServiceBrandList:
    """BRAND-LIST: 品牌列表测试"""

    def test_get_all_brands_returns_all_builtin(self):
        """BRAND-LIST-01: get_all_brands 返回所有内置品牌"""
        svc = make_brand_service()
        brands = svc.get_all_brands()
        assert len(brands) == len(BUILTIN_BRANDS)

    def test_brand_list_has_required_fields(self):
        """BRAND-LIST-02: 每个品牌项包含必要字段"""
        svc = make_brand_service()
        brands = svc.get_all_brands()
        required_fields = {"brand_key", "brand_name", "brand_name_en", "verify_type", "description"}
        for brand in brands:
            assert required_fields.issubset(brand.keys()), f"品牌 {brand['brand_key']} 缺少必要字段"


class TestBrandVerifyServiceLookup:
    """BRAND-LOOKUP: 品牌查找/匹配测试"""

    def test_lookup_by_chinese_name(self):
        """BRAND-LOOKUP-01: 通过中文名查找品牌"""
        svc = make_brand_service()
        info = svc.get_brand_verify_info("兰蔻")
        assert info is not None
        assert info["brand_key"] == "lancome"
        assert info["brand_name"] == "兰蔻"

    def test_lookup_by_english_name(self):
        """BRAND-LOOKUP-02: 通过英文名查找品牌"""
        svc = make_brand_service()
        info = svc.get_brand_verify_info("Lancôme")
        assert info is not None
        assert info["brand_key"] == "lancome"

    def test_lookup_by_brand_key(self):
        """BRAND-LOOKUP-03: 通过 brand_key 查找品牌"""
        svc = make_brand_service()
        info = svc.get_brand_verify_info("loreal")
        assert info is not None
        assert info["brand_name"] == "欧莱雅"

    def test_lookup_case_insensitive(self):
        """BRAND-LOOKUP-04: 查找不区分大小写"""
        svc = make_brand_service()
        info = svc.get_brand_verify_info("CHANEL")
        assert info is not None
        assert info["brand_key"] == "chanel"

    def test_lookup_with_whitespace_stripped(self):
        """BRAND-LOOKUP-05: 品牌名前后空格被去除"""
        svc = make_brand_service()
        info = svc.get_brand_verify_info("  迪奥  ")
        assert info is not None
        assert info["brand_key"] == "dior"

    def test_lookup_unknown_brand_returns_none(self):
        """BRAND-LOOKUP-06: 未知品牌 → 返回 None"""
        svc = make_brand_service()
        info = svc.get_brand_verify_info("不存在的品牌")
        assert info is None

    def test_lookup_returns_verify_info_fields(self):
        """BRAND-LOOKUP-07: 返回信息包含验证所需字段"""
        svc = make_brand_service()
        info = svc.get_brand_verify_info("SK-II")
        assert info is not None
        assert info["verify_type"] == "url"
        assert info["verify_url"] is not None
        assert "description" in info

    def test_lookup_miniprogram_type_has_appid(self):
        """BRAND-LOOKUP-08: miniprogram 类型品牌包含 miniprogram_id"""
        svc = make_brand_service()
        info = svc.get_brand_verify_info("欧莱雅")
        assert info is not None
        assert info["verify_type"] == "miniprogram"
        assert info["miniprogram_id"] is not None
        assert info["miniprogram_path"] is not None

    def test_all_builtin_brands_matchable(self):
        """BRAND-LOOKUP-09: 所有内置品牌均可通过名称查找"""
        svc = make_brand_service()
        for b in BUILTIN_BRANDS:
            # 中文名查找
            info = svc.get_brand_verify_info(b["brand_name"])
            assert info is not None, f"品牌 {b['brand_name']} 无法通过中文名查找"
            # key 查找
            info = svc.get_brand_verify_info(b["brand_key"])
            assert info is not None, f"品牌 {b['brand_key']} 无法通过 key 查找"


class TestBrandVerifyServiceCodePattern:
    """BRAND-CODE: 防伪码格式自动识别测试"""

    def test_match_brand_by_code_no_patterns(self):
        """BRAND-CODE-01: 所有内置品牌均无 code_pattern → 总是返回 None"""
        svc = make_brand_service()
        # 当前内置品牌全部 code_pattern=None，所以匹配任何码都应返回 None
        result = svc.match_brand_by_code("LOREAL-ABC123-XYZ")
        assert result is None

    def test_match_brand_by_code_empty_string(self):
        """BRAND-CODE-02: 空防伪码 → 返回 None"""
        svc = make_brand_service()
        result = svc.match_brand_by_code("")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# F3 — BarcodeRequest Schema 校验
# ══════════════════════════════════════════════════════════════════════════════

class TestBarcodeRequestValidation:
    """BARCODE-SCHEMA: 条形码请求格式校验"""

    def test_valid_ean13(self):
        """BARCODE-SCHEMA-01: EAN-13 合法条形码"""
        req = BarcodeRequest(barcode="3337875597371")
        assert req.barcode == "3337875597371"

    def test_valid_ean8(self):
        """BARCODE-SCHEMA-02: EAN-8 合法条形码"""
        req = BarcodeRequest(barcode="12345678")
        assert req.barcode == "12345678"

    def test_valid_upc_a(self):
        """BARCODE-SCHEMA-03: UPC-A 12 位合法条形码"""
        req = BarcodeRequest(barcode="012345678901")
        assert req.barcode == "012345678901"

    def test_valid_14_digits(self):
        """BARCODE-SCHEMA-04: 14 位条形码（GTIN-14）"""
        req = BarcodeRequest(barcode="12345678901234")
        assert req.barcode == "12345678901234"

    def test_strips_whitespace(self):
        """BARCODE-SCHEMA-05: 前后空格被去除"""
        req = BarcodeRequest(barcode="  3337875597371  ")
        assert req.barcode == "3337875597371"

    def test_too_short_rejected(self):
        """BARCODE-SCHEMA-06: 少于 8 位 → 校验失败"""
        with pytest.raises(ValueError):
            BarcodeRequest(barcode="1234567")

    def test_too_long_rejected(self):
        """BARCODE-SCHEMA-07: 超过 14 位 → 校验失败"""
        with pytest.raises(ValueError):
            BarcodeRequest(barcode="123456789012345")

    def test_alpha_chars_rejected(self):
        """BARCODE-SCHEMA-08: 包含字母 → 校验失败"""
        with pytest.raises(ValueError):
            BarcodeRequest(barcode="33378755ABC")

    def test_empty_string_rejected(self):
        """BARCODE-SCHEMA-09: 空字符串 → 校验失败"""
        with pytest.raises(ValueError):
            BarcodeRequest(barcode="")

    def test_special_chars_rejected(self):
        """BARCODE-SCHEMA-10: 包含特殊字符 → 校验失败"""
        with pytest.raises(ValueError):
            BarcodeRequest(barcode="3337-875-5973")


# ══════════════════════════════════════════════════════════════════════════════
# F4 — BrandVerifyRequest Schema 校验
# ══════════════════════════════════════════════════════════════════════════════

class TestBrandVerifyRequestValidation:
    """BRAND-SCHEMA: 品牌防伪请求格式校验"""

    def test_valid_brand_name_only(self):
        """BRAND-SCHEMA-01: 仅品牌名"""
        req = BrandVerifyRequest(brand_name="兰蔻")
        assert req.brand_name == "兰蔻"
        assert req.code is None

    def test_valid_brand_name_with_code(self):
        """BRAND-SCHEMA-02: 品牌名 + 防伪码"""
        req = BrandVerifyRequest(brand_name="欧莱雅", code="ABC123XYZ")
        assert req.brand_name == "欧莱雅"
        assert req.code == "ABC123XYZ"

    def test_empty_brand_name_rejected(self):
        """BRAND-SCHEMA-03: 空品牌名 → 校验失败"""
        with pytest.raises(ValueError):
            BrandVerifyRequest(brand_name="   ")

    def test_brand_name_stripped(self):
        """BRAND-SCHEMA-04: 品牌名前后空格被去除"""
        req = BrandVerifyRequest(brand_name="  香奈儿  ")
        assert req.brand_name == "香奈儿"


# ══════════════════════════════════════════════════════════════════════════════
# F5 — API 端点集成测试（使用 conftest 提供的 client fixture）
# ══════════════════════════════════════════════════════════════════════════════

# 生成测试用 JWT token
def _make_auth_header():
    from app.core.security import create_access_token
    token = create_access_token({"sub": "1", "openid": "test_openid_001"})
    return {"Authorization": f"Bearer {token}"}


class TestBarcodeEndpoint:
    """API-BARCODE: POST /api/v1/anti-fake/barcode"""

    @pytest.mark.asyncio
    async def test_barcode_found(self, client, mock_redis):
        """API-BARCODE-01: 条形码查询成功 → 返回产品信息"""
        # mock redis cache hit with product data
        cached_product = json.dumps({
            "barcode": SAMPLE_BARCODE,
            "product_name": "CeraVe Moisturizing Cream",
            "brand": "CeraVe",
            "category": "Moisturizers",
            "image_url": None,
            "ingredients": "Aqua, Glycerin",
            "labels": None,
            "quantity": "50ml",
            "source": "Open Beauty Facts",
            "source_url": f"https://world.openbeautyfacts.org/product/{SAMPLE_BARCODE}",
        })
        mock_redis.get.return_value = cached_product

        resp = await client.post(
            "/api/v1/anti-fake/barcode",
            json={"barcode": SAMPLE_BARCODE},
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["found"] is True
        assert body["data"]["product"]["product_name"] == "CeraVe Moisturizing Cream"

    @pytest.mark.asyncio
    async def test_barcode_not_found(self, client, mock_redis):
        """API-BARCODE-02: 条形码未收录 → code=2001"""
        mock_redis.get.return_value = '"__MISS__"'

        resp = await client.post(
            "/api/v1/anti-fake/barcode",
            json={"barcode": SAMPLE_MISSING_BARCODE},
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 2001
        assert body["data"]["found"] is False

    @pytest.mark.asyncio
    async def test_barcode_invalid_format(self, client):
        """API-BARCODE-03: 非法条形码 → 422"""
        resp = await client.post(
            "/api/v1/anti-fake/barcode",
            json={"barcode": "abc"},
            headers=_make_auth_header(),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_barcode_no_auth(self, client):
        """API-BARCODE-04: 无 token → 401/403"""
        resp = await client.post(
            "/api/v1/anti-fake/barcode",
            json={"barcode": SAMPLE_BARCODE},
        )
        assert resp.status_code in (401, 403)


class TestBrandVerifyEndpoint:
    """API-BRAND: POST /api/v1/anti-fake/brand-verify"""

    @pytest.mark.asyncio
    async def test_brand_found(self, client, mock_redis):
        """API-BRAND-01: 已知品牌 → 返回跳转信息"""
        mock_redis.get.return_value = None

        resp = await client.post(
            "/api/v1/anti-fake/brand-verify",
            json={"brand_name": "兰蔻"},
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["found"] is True
        assert body["data"]["brand"]["brand_key"] == "lancome"

    @pytest.mark.asyncio
    async def test_brand_not_found(self, client, mock_redis):
        """API-BRAND-02: 未知品牌 → code=2004"""
        mock_redis.get.return_value = None

        resp = await client.post(
            "/api/v1/anti-fake/brand-verify",
            json={"brand_name": "虚构品牌ABC"},
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 2004
        assert body["data"]["found"] is False

    @pytest.mark.asyncio
    async def test_brand_with_code(self, client, mock_redis):
        """API-BRAND-03: 品牌名 + 防伪码 → 正常返回"""
        mock_redis.get.return_value = None

        resp = await client.post(
            "/api/v1/anti-fake/brand-verify",
            json={"brand_name": "SK-II", "code": "SKII12345"},
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["found"] is True

    @pytest.mark.asyncio
    async def test_brand_no_auth(self, client):
        """API-BRAND-04: 无 token → 401/403"""
        resp = await client.post(
            "/api/v1/anti-fake/brand-verify",
            json={"brand_name": "兰蔻"},
        )
        assert resp.status_code in (401, 403)


class TestBrandsListEndpoint:
    """API-BRANDS: GET /api/v1/anti-fake/brands"""

    @pytest.mark.asyncio
    async def test_list_brands(self, client, mock_redis):
        """API-BRANDS-01: 获取品牌列表（无需登录）"""
        mock_redis.get.return_value = None

        resp = await client.get("/api/v1/anti-fake/brands")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["total"] == len(BUILTIN_BRANDS)
        assert len(body["data"]["brands"]) == len(BUILTIN_BRANDS)

    @pytest.mark.asyncio
    async def test_brands_have_required_fields(self, client, mock_redis):
        """API-BRANDS-02: 品牌列表项包含必要字段"""
        mock_redis.get.return_value = None

        resp = await client.get("/api/v1/anti-fake/brands")
        body = resp.json()
        for brand in body["data"]["brands"]:
            assert "brand_key" in brand
            assert "brand_name" in brand
            assert "brand_name_en" in brand
            assert "verify_type" in brand


class TestHistoryEndpoint:
    """API-HISTORY: GET /api/v1/anti-fake/history"""

    @pytest.mark.asyncio
    async def test_history_empty(self, client, mock_redis):
        """API-HISTORY-01: 无历史记录 → 空列表"""
        resp = await client.get(
            "/api/v1/anti-fake/history",
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] == 0
        assert body["data"]["items"] == []

    @pytest.mark.asyncio
    async def test_history_after_barcode_query(self, client, mock_redis):
        """API-HISTORY-02: 条形码查询后历史中有记录"""
        # 先做一次条形码查询（会写入历史）
        mock_redis.get.return_value = '"__MISS__"'
        await client.post(
            "/api/v1/anti-fake/barcode",
            json={"barcode": SAMPLE_BARCODE},
            headers=_make_auth_header(),
        )

        # 查历史
        resp = await client.get(
            "/api/v1/anti-fake/history",
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] >= 1
        item = body["data"]["items"][0]
        assert item["query_type"] == "barcode"
        assert item["query_value"] == SAMPLE_BARCODE

    @pytest.mark.asyncio
    async def test_history_after_brand_query(self, client, mock_redis):
        """API-HISTORY-03: 品牌查询后历史中有记录"""
        mock_redis.get.return_value = None
        await client.post(
            "/api/v1/anti-fake/brand-verify",
            json={"brand_name": "迪奥"},
            headers=_make_auth_header(),
        )

        resp = await client.get(
            "/api/v1/anti-fake/history",
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] >= 1
        item = body["data"]["items"][0]
        assert item["query_type"] == "brand_redirect"
        assert "迪奥" in item["query_value"]

    @pytest.mark.asyncio
    async def test_history_pagination(self, client, mock_redis):
        """API-HISTORY-04: 分页参数生效"""
        resp = await client.get(
            "/api/v1/anti-fake/history?page=1&size=5",
            headers=_make_auth_header(),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_history_no_auth(self, client):
        """API-HISTORY-05: 无 token → 401/403"""
        resp = await client.get("/api/v1/anti-fake/history")
        assert resp.status_code in (401, 403)
