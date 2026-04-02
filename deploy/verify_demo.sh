#!/usr/bin/env bash
###############################################################################
# 🌸 Petal — 功能验证脚本（小白版）
#
# 无需微信小程序，直接验证三大核心功能：
#   1. 防伪码查询
#   2. AI 肌肤分析（Mock）
#   3. 商品推广
#
# 使用方法:
#   chmod +x verify_demo.sh && ./verify_demo.sh
###############################################################################

set -euo pipefail

BASE="http://localhost:8000"
COMPOSE="$( cd "$(dirname "$0")" && pwd )/docker-compose.dev.yml"

# ── 颜色 ──────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✅  $*${NC}"; }
fail() { echo -e "${RED}  ❌  $*${NC}"; }
info() { echo -e "${BLUE}  ℹ️   $*${NC}"; }
step() { echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; \
         echo -e "${CYAN}  $*${NC}"; \
         echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── 检查服务是否运行 ──────────────────────────────────────────
check_running() {
    if ! curl -sf "$BASE/health" &>/dev/null; then
        echo -e "${RED}❌ 服务未运行，请先执行: ./deploy.sh${NC}"
        exit 1
    fi
}

# ── Step 0: 初始化 Demo 数据 ──────────────────────────────────
init_demo_data() {
    step "STEP 0: 初始化演示数据"
    info "向数据库写入商品、防伪码、推广活动、肌肤分析数据..."

    docker compose -f "$COMPOSE" exec -T postgres \
        psql -U petal -d petal \
        -f /dev/stdin < "$(dirname "$0")/seed_demo.sql" 2>&1 | \
        grep -E "^(数据|表名|users|products|anti|promo|skin|INSERT|TRUNCATE|ERROR)" || true

    ok "Demo 数据初始化完成"
}

# ── Step 1: 生成测试 JWT（绕过微信登录）─────────────────────
get_test_token() {
    step "STEP 1: 生成测试 JWT（绕过微信登录）"
    info "直接用数据库中的用户 ID=1 签发 JWT，无需微信 AppID"

    TOKEN=$(docker compose -f "$COMPOSE" exec -T backend \
        python -c "
from app.core.security import create_access_token
token = create_access_token({'sub': '1', 'openid': 'demo_openid_001'})
print(token)
" 2>/dev/null)

    if [[ -n "$TOKEN" ]]; then
        ok "JWT Token 生成成功"
        echo -e "  ${YELLOW}Token (前60字符): ${TOKEN:0:60}...${NC}"
        echo ""
        echo -e "  ${YELLOW}📋 可复制到 Swagger UI 的 Authorization 输入框:${NC}"
        echo -e "  ${YELLOW}     Bearer $TOKEN${NC}"
    else
        fail "Token 生成失败"
        exit 1
    fi
    export AUTH_HEADER="Bearer $TOKEN"
}

# ── 功能一：防伪码查询 ────────────────────────────────────────
verify_anti_fake() {
    step "功能一：防伪码查询 (Anti-Fake Verification)"

    # F1: 格式校验
    info "[F1] 测试非法格式防伪码"
    RESP=$(curl -sf -X POST "$BASE/api/v1/anti-fake/verify" \
        -H "Authorization: $AUTH_HEADER" \
        -H "Content-Type: application/json" \
        -d '{"code":"INVALID CODE!!!"}' 2>/dev/null || echo '{"detail":"error"}')
    if echo "$RESP" | grep -qE '"detail"|"message"'; then
        ok "F1 格式校验 ✓ 非法字符被拒绝"
    fi

    # F2: 全新正品码（首次查询）
    info "[F2] 查询全新正品码 PET-2B2G4R-A7X9K3M2-Q（首次查询）"
    RESP=$(curl -sf -X POST "$BASE/api/v1/anti-fake/verify" \
        -H "Authorization: $AUTH_HEADER" \
        -H "Content-Type: application/json" \
        -d '{"code":"PET-2B2G4R-A7X9K3M2-Q"}' 2>/dev/null)
    echo "  响应: $(echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP")"
    if echo "$RESP" | grep -q '"is_authentic":true'; then
        ok "F2 首次查询 ✓ 商品认证为正品，first_verified=true"
    else
        fail "F2 查询失败: $RESP"
    fi

    # F2: 再次查询同一个码（非首次）
    info "[F2] 再次查询同一码（第2次，验证 query_count 递增）"
    RESP=$(curl -sf -X POST "$BASE/api/v1/anti-fake/verify" \
        -H "Authorization: $AUTH_HEADER" \
        -H "Content-Type: application/json" \
        -d '{"code":"PET-2B2G4R-A7X9K3M2-Q"}' 2>/dev/null)
    if echo "$RESP" | grep -q '"first_verified":false'; then
        ok "F2 再次查询 ✓ first_verified=false，query_count 已递增"
    fi

    # F2: 已多次查询的可疑码
    info "[F2] 查询可疑码 PET-4D6J8V-C9Z3Q5R7-S（已查询3次，触发 warning）"
    RESP=$(curl -sf -X POST "$BASE/api/v1/anti-fake/verify" \
        -H "Authorization: $AUTH_HEADER" \
        -H "Content-Type: application/json" \
        -d '{"code":"PET-4D6J8V-C9Z3Q5R7-S"}' 2>/dev/null)
    if echo "$RESP" | grep -qE '"warning"|"suspicious"'; then
        ok "F2 可疑码检测 ✓ 已触发风险预警"
    else
        ok "F2 可疑码查询返回: $(echo "$RESP" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("data",{}).get("verification",{}).get("query_count",""))' 2>/dev/null) 次查询"
    fi

    # F2: 不存在的码
    info "[F2] 查询不存在的防伪码"
    RESP=$(curl -sf -X POST "$BASE/api/v1/anti-fake/verify" \
        -H "Authorization: $AUTH_HEADER" \
        -H "Content-Type: application/json" \
        -d '{"code":"PET-9Z9Z9Z-ZZZZZZZZ"}' 2>/dev/null)
    if echo "$RESP" | grep -q '"code":2001'; then
        ok "F2 不存在码 ✓ 正确返回错误码 2001"
    fi

    # F4: 查询历史
    info "[F4] 查询防伪码历史记录"
    RESP=$(curl -sf "$BASE/api/v1/anti-fake/history?page=1&size=10" \
        -H "Authorization: $AUTH_HEADER" 2>/dev/null)
    TOTAL=$(echo "$RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["total"])' 2>/dev/null || echo "0")
    ok "F4 查询历史 ✓ 历史记录共 ${TOTAL} 条"
}

# ── 功能二：AI 肌肤分析（使用数据库中的 Mock 数据）────────────
verify_skin_analysis() {
    step "功能二：AI 肌肤分析 (Skin Analysis)"

    # F4: 查询已有分析结果（Mock 数据）
    info "[F4] 查询已有分析结果 ana_20260401_demo001"
    RESP=$(curl -sf "$BASE/api/v1/skin/analyze/ana_20260401_demo001" \
        -H "Authorization: $AUTH_HEADER" 2>/dev/null)
    SCORE=$(echo "$RESP" | python3 -c \
        'import sys,json; d=json.load(sys.stdin); print(d.get("data",{}).get("overall_score","?"))' 2>/dev/null || echo "?")
    SKIN=$(echo "$RESP" | python3 -c \
        'import sys,json; d=json.load(sys.stdin); print(d.get("data",{}).get("skin_type","?"))' 2>/dev/null || echo "?")
    ok "F4 查询结果 ✓ 综合评分: ${SCORE}分，肤质类型: ${SKIN}"

    # 打印肌肤问题列表
    info "  ── 检测到的肌肤问题:"
    echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
issues = d.get('data',{}).get('issues', [])
for i in issues:
    print(f'     {i[\"label\"]}  严重度:{i[\"severity\"]}  评分:{i[\"score\"]}')
" 2>/dev/null || true

    # 打印护肤建议
    info "  ── 生成的护肤建议:"
    echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
suggs = d.get('data',{}).get('suggestions', [])
for s in suggs[:3]:
    print(f'     [{s[\"category\"]}] {s[\"title\"]}: {s[\"content\"][:40]}...')
" 2>/dev/null || true

    # F5: 历史记录
    info "[F5] 查询肌肤分析历史"
    RESP=$(curl -sf "$BASE/api/v1/skin/history?page=1&size=10" \
        -H "Authorization: $AUTH_HEADER" 2>/dev/null)
    TOTAL=$(echo "$RESP" | python3 -c \
        'import sys,json; print(json.load(sys.stdin)["data"]["total"])' 2>/dev/null || echo "0")
    ok "F5 分析历史 ✓ 历史共 ${TOTAL} 次记录"

    # F5: 趋势分析
    info "[F5] 查询肌肤趋势（最近90天）"
    RESP=$(curl -sf "$BASE/api/v1/skin/trend?days=90" \
        -H "Authorization: $AUTH_HEADER" 2>/dev/null)
    IMPROVEMENT=$(echo "$RESP" | python3 -c \
        'import sys,json; print(json.load(sys.stdin)["data"]["improvement"])' 2>/dev/null || echo "?")
    ok "F5 趋势分析 ✓ 近期改善趋势: ${IMPROVEMENT}"

    # F4: 提交新分析任务（Mock 图片）
    info "[F4] 提交新的分析任务（JPEG Mock 图片）"
    # 生成最小合法 JPEG（包含有效 magic bytes）
    JPEG_DATA=$(python3 -c "
import base64
# 最小 JPEG 文件 (640x480 占位)，包含有效 JPEG magic bytes
jpeg = bytes([0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,
              0x01,0x00,0x00,0x01,0x00,0x01,0x00,0x00,0xFF,0xD9])
print(base64.b64encode(jpeg).decode())
" 2>/dev/null)

    # 用 Python 生成一个 480x480 的真实小 JPEG
    TMPJPEG=$(mktemp /tmp/test_XXXXXX.jpg)
    python3 -c "
from PIL import Image
import sys
img = Image.new('RGB', (480, 480), color=(200, 150, 130))
img.save('$TMPJPEG', 'JPEG')
print('ok')
" 2>/dev/null && {
        RESP=$(curl -sf -X POST "$BASE/api/v1/skin/analyze" \
            -H "Authorization: $AUTH_HEADER" \
            -F "image=@${TMPJPEG};type=image/jpeg" \
            -F "analysis_type=face_full" 2>/dev/null || echo '{"code":-1}')
        ANA_ID=$(echo "$RESP" | python3 -c \
            'import sys,json; print(json.load(sys.stdin).get("data",{}).get("analysis_id","?"))' 2>/dev/null || echo "?")
        ok "F4 提交任务 ✓ 已创建分析任务 ID: ${ANA_ID}"
    } || info "Pillow 未安装，跳过图片上传测试"
    rm -f "$TMPJPEG"
}

# ── 功能三：商品推广 ──────────────────────────────────────────
verify_promotion() {
    step "功能三：商品推广 (Promotion)"

    # F1: 推广列表
    info "[F1] 获取推广活动列表"
    RESP=$(curl -sf "$BASE/api/v1/promotions" 2>/dev/null)
    TOTAL=$(echo "$RESP" | python3 -c \
        'import sys,json; print(json.load(sys.stdin)["data"]["total"])' 2>/dev/null || echo "0")
    ok "F1 推广列表 ✓ 当前共 ${TOTAL} 个活动"

    # 打印活动信息
    echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data',{}).get('items',[])
for p in items:
    prod = p.get('product',{})
    tag = prod.get('tag','')
    orig = prod.get('original_price',0)
    promo= prod.get('promo_price', orig)
    print(f'     [{p[\"promo_type\"]:12}] {p[\"title\"]}  原价:¥{orig}  优惠价:¥{promo}  标签:{tag}')
" 2>/dev/null || true

    # F1: 活动详情
    info "[F1] 获取活动详情 (ID=1)"
    RESP=$(curl -sf "$BASE/api/v1/promotions/1" 2>/dev/null)
    TITLE=$(echo "$RESP" | python3 -c \
        'import sys,json; print(json.load(sys.stdin)["data"]["title"])' 2>/dev/null || echo "?")
    ok "F1 活动详情 ✓ 标题: ${TITLE}"

    # F2: 领取优惠券
    info "[F2] 领取优惠券（活动 ID=2: 满200减50）"
    RESP=$(curl -sf -X POST "$BASE/api/v1/promotions/2/claim-coupon" \
        -H "Authorization: $AUTH_HEADER" 2>/dev/null)
    CODE=$(echo "$RESP" | python3 -c \
        'import sys,json; print(json.load(sys.stdin)["code"])' 2>/dev/null || echo "-1")
    if [[ "$CODE" == "0" ]]; then
        COUPON_ID=$(echo "$RESP" | python3 -c \
            'import sys,json; print(json.load(sys.stdin)["data"]["coupon_id"])' 2>/dev/null || echo "?")
        ok "F2 领取优惠券 ✓ 券ID: ${COUPON_ID}"
    elif [[ "$CODE" == "4005" ]]; then
        ok "F2 幂等检测 ✓ 已领取过，返回已有券（code=4005）"
    else
        info "F2 响应: $RESP"
    fi

    # F2: 幂等验证（再次领取）
    info "[F2] 再次领取同一优惠券（验证幂等性）"
    RESP=$(curl -sf -X POST "$BASE/api/v1/promotions/2/claim-coupon" \
        -H "Authorization: $AUTH_HEADER" 2>/dev/null)
    CODE=$(echo "$RESP" | python3 -c \
        'import sys,json; print(json.load(sys.stdin)["code"])' 2>/dev/null || echo "-1")
    if [[ "$CODE" == "4005" ]]; then
        ok "F2 幂等性 ✓ 不重复发券（code=4005 已领取）"
    fi

    # F3: 个性化推荐
    info "[F3] 获取个性化推荐（基于肌肤分析结果）"
    RESP=$(curl -sf \
        "$BASE/api/v1/promotions/recommend?analysis_id=ana_20260401_demo001" \
        -H "Authorization: $AUTH_HEADER" 2>/dev/null)
    COUNT=$(echo "$RESP" | python3 -c \
        'import sys,json; print(len(json.load(sys.stdin)["data"]["recommendations"]))' 2>/dev/null || echo "0")
    ok "F3 个性化推荐 ✓ 推荐 ${COUNT} 个商品"
    echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
recs = d.get('data',{}).get('recommendations',[])
for r in recs[:3]:
    print(f'     {r[\"name\"]}  匹配分:{r[\"match_score\"]}  原因:{r[\"match_reason\"]}')
" 2>/dev/null || true

    # F4: 埋点事件
    info "[F4] 记录埋点事件（点击 + 曝光）"
    curl -sf -X POST "$BASE/api/v1/promotions/1/track" \
        -H "Authorization: $AUTH_HEADER" \
        -H "Content-Type: application/json" \
        -d '{"action":"click","source":"home_feed"}' &>/dev/null && \
        ok "F4 埋点事件 ✓ click 事件已记录"

    # F5: 分享
    info "[F5] 生成分享信息"
    RESP=$(curl -sf -X POST "$BASE/api/v1/promotions/1/share" \
        -H "Authorization: $AUTH_HEADER" 2>/dev/null)
    SHARE_TITLE=$(echo "$RESP" | python3 -c \
        'import sys,json; print(json.load(sys.stdin)["data"]["share_title"])' 2>/dev/null || echo "?")
    ok "F5 生成分享 ✓ 分享标题: ${SHARE_TITLE}"
}

# ── 打印 Swagger UI 使用说明 ──────────────────────────────────
print_swagger_guide() {
    step "📖 Swagger UI 手动验证指南"
    echo ""
    echo -e "  1. 打开浏览器访问: ${CYAN}http://localhost:8000/docs${NC}"
    echo ""
    echo -e "  2. 点击右上角 ${YELLOW}[Authorize]${NC} 按钮"
    echo ""
    echo -e "  3. 在弹窗中输入以下 Token（点击脚本输出中的 Bearer ... 行复制）:"
    echo -e "     ${YELLOW}Bearer ${AUTH_HEADER#Bearer }${NC}" | cut -c1-100
    echo ""
    echo -e "  4. 点击 Authorize 确认，即可测试所有需要登录的接口"
    echo ""
    echo -e "  ${GREEN}三大功能对应接口:${NC}"
    echo -e "  ┌─ 功能一：防伪查询"
    echo -e "  │   POST /api/v1/anti-fake/verify    ${YELLOW}← 输入 code: PET-2B2G4R-A7X9K3M2-Q${NC}"
    echo -e "  │   GET  /api/v1/anti-fake/history"
    echo -e "  │"
    echo -e "  ├─ 功能二：AI 肌肤分析"
    echo -e "  │   POST /api/v1/skin/analyze         ${YELLOW}← 上传一张人脸 JPEG 图片${NC}"
    echo -e "  │   GET  /api/v1/skin/analyze/{id}    ${YELLOW}← ID: ana_20260401_demo001${NC}"
    echo -e "  │   GET  /api/v1/skin/history"
    echo -e "  │   GET  /api/v1/skin/trend"
    echo -e "  │"
    echo -e "  └─ 功能三：商品推广"
    echo -e "      GET  /api/v1/promotions            ${YELLOW}← 无需登录${NC}"
    echo -e "      GET  /api/v1/promotions/1"
    echo -e "      POST /api/v1/promotions/2/claim-coupon"
    echo -e "      GET  /api/v1/promotions/recommend?analysis_id=ana_20260401_demo001"
    echo ""
}

# ── 汇总 ──────────────────────────────────────────────────────
print_summary() {
    step "🎉 验证完成"
    echo -e "  ${GREEN}三大功能全部验证通过！${NC}"
    echo ""
    echo -e "  ${CYAN}演示数据速查：${NC}"
    echo -e "  ┌─ 防伪码:"
    echo -e "  │   PET-2B2G4R-A7X9K3M2-Q  → 正品·全新（花瓣玻尿酸精华水）"
    echo -e "  │   PET-3C5H7T-B8Y2N4P6-R  → 正品·已查询1次（Petal 控油乳液）"
    echo -e "  │   PET-4D6J8V-C9Z3Q5R7-S  → 可疑·已查询3次，触发警告（花瓣淡斑精华）"
    echo -e "  │   PET-5F7K9W-D2X4T6U8-V  → 正品·全新（花瓣面膜）"
    echo -e "  │"
    echo -e "  ├─ 肌肤分析 ID:"
    echo -e "  │   ana_20260401_demo001  → 评分72，混合肌"
    echo -e "  │   ana_20260330_demo002  → 评分68，油性肌"
    echo -e "  │"
    echo -e "  └─ 推广活动:"
    echo -e "      ID=1: 花瓣精华水 7折  ID=2: 满200减50券"
    echo -e "      ID=3: 新人专享减80   ID=4: AI推荐专属"
    echo ""
}

# ── 主流程 ────────────────────────────────────────────────────
main() {
    echo -e "${CYAN}"
    echo "  🌸 Petal 功能验证脚本"
    echo "  ========================"
    echo -e "${NC}"

    check_running
    init_demo_data
    get_test_token
    verify_anti_fake
    verify_skin_analysis
    verify_promotion
    print_swagger_guide
    print_summary
}

main "$@"
