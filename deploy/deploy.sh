#!/usr/bin/env bash
###############################################################################
# 🌸 Petal — 一键部署脚本
# 
# 使用说明:
#   chmod +x deploy.sh && ./deploy.sh
#
# 前置条件:
#   - Docker >= 20.10
#   - Docker Compose >= 2.0 (docker compose V2)
#   - 可用端口: 80(Nginx), 8000(API), 5432(PG), 6379(Redis), 9000/9001(MinIO)
#
# 支持命令:
#   ./deploy.sh           # 一键部署（默认）
#   ./deploy.sh start     # 启动服务
#   ./deploy.sh stop      # 停止服务
#   ./deploy.sh restart   # 重启服务
#   ./deploy.sh status    # 查看服务状态
#   ./deploy.sh logs      # 查看日志
#   ./deploy.sh test      # 运行测试
#   ./deploy.sh clean     # 停止并清除所有数据
#   ./deploy.sh health    # 健康检查
###############################################################################

set -euo pipefail

# ── 颜色定义 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── 项目路径 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/backend"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.dev.yml"

# ── 工具函数 ──────────────────────────────────────────────────────────────────
log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_success() { echo -e "${GREEN}[✅]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()    { echo -e "\n${CYAN}━━━ $* ━━━${NC}"; }

# ── 前置检查 ──────────────────────────────────────────────────────────────────
check_prerequisites() {
    log_step "检查前置依赖"

    # Docker
    if ! command -v docker &>/dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        echo "  安装指南: https://docs.docker.com/engine/install/"
        exit 1
    fi
    local docker_ver
    docker_ver=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
    log_success "Docker 已安装 (v${docker_ver})"

    # Docker Compose V2
    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose V2 未安装"
        echo "  安装指南: https://docs.docker.com/compose/install/"
        exit 1
    fi
    local compose_ver
    compose_ver=$(docker compose version --short 2>/dev/null || echo "unknown")
    log_success "Docker Compose 已安装 (v${compose_ver})"

    # 检查端口占用
    local ports=(80 8000 5432 6379 9000 9001)
    local occupied=()
    for port in "${ports[@]}"; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} " || \
           netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
            occupied+=("$port")
        fi
    done
    if [[ ${#occupied[@]} -gt 0 ]]; then
        log_warn "以下端口已被占用: ${occupied[*]}"
        log_warn "请确保没有冲突的服务在运行，或修改 docker-compose.dev.yml 中的端口映射"
    else
        log_success "所有需要的端口可用 (${ports[*]})"
    fi

    # 检查磁盘空间 (至少需要 2GB)
    local available_gb
    available_gb=$(df -BG "$PROJECT_ROOT" | awk 'NR==2 {gsub(/G/,"",$4); print $4}')
    if [[ "$available_gb" -lt 2 ]]; then
        log_warn "可用磁盘空间不足 2GB (当前: ${available_gb}GB)"
    else
        log_success "磁盘空间充足 (${available_gb}GB 可用)"
    fi
}

# ── 构建并启动 ────────────────────────────────────────────────────────────────
deploy() {
    log_step "开始部署 Petal 美妆平台"

    check_prerequisites

    log_step "构建并启动服务"
    cd "$DEPLOY_DIR"
    docker compose -f "$COMPOSE_FILE" up -d --build 2>&1

    log_step "等待服务就绪"
    wait_for_services

    log_step "验证部署"
    health_check

    print_summary
}

# ── 等待服务就绪 ──────────────────────────────────────────────────────────────
wait_for_services() {
    local max_wait=120
    local elapsed=0

    # 等待 PostgreSQL
    log_info "等待 PostgreSQL 就绪..."
    while ! docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U petal &>/dev/null; do
        sleep 2
        elapsed=$((elapsed + 2))
        if [[ $elapsed -ge $max_wait ]]; then
            log_error "PostgreSQL 启动超时 (${max_wait}s)"
            exit 1
        fi
    done
    log_success "PostgreSQL 就绪"

    # 等待 Redis
    log_info "等待 Redis 就绪..."
    elapsed=0
    while ! docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping &>/dev/null; do
        sleep 2
        elapsed=$((elapsed + 2))
        if [[ $elapsed -ge $max_wait ]]; then
            log_error "Redis 启动超时 (${max_wait}s)"
            exit 1
        fi
    done
    log_success "Redis 就绪"

    # 等待 Backend
    log_info "等待 Backend API 就绪..."
    elapsed=0
    while ! curl -sf http://localhost:8000/health &>/dev/null; do
        sleep 3
        elapsed=$((elapsed + 3))
        if [[ $elapsed -ge $max_wait ]]; then
            log_error "Backend 启动超时 (${max_wait}s)"
            log_info "查看日志: docker compose -f $COMPOSE_FILE logs backend"
            exit 1
        fi
    done
    log_success "Backend API 就绪"

    # 等待 Nginx
    log_info "等待 Nginx 就绪..."
    elapsed=0
    while ! curl -sf http://localhost:80/health &>/dev/null; do
        sleep 2
        elapsed=$((elapsed + 2))
        if [[ $elapsed -ge $max_wait ]]; then
            log_error "Nginx 启动超时 (${max_wait}s)"
            exit 1
        fi
    done
    log_success "Nginx 网关就绪"
}

# ── 健康检查 ──────────────────────────────────────────────────────────────────
health_check() {
    local all_ok=true

    log_step "服务健康检查"

    # Backend health
    local resp
    resp=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "FAIL")
    if echo "$resp" | grep -q '"status":"ok"'; then
        log_success "Backend API     ✓  http://localhost:8000/health"
    else
        log_error "Backend API     ✗  http://localhost:8000/health"
        all_ok=false
    fi

    # Nginx gateway
    resp=$(curl -sf http://localhost:80/health 2>/dev/null || echo "FAIL")
    if echo "$resp" | grep -q '"status":"ok"'; then
        log_success "Nginx Gateway   ✓  http://localhost:80/health"
    else
        log_error "Nginx Gateway   ✗  http://localhost:80/health"
        all_ok=false
    fi

    # Swagger docs
    local docs_code
    docs_code=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8000/docs 2>/dev/null || echo "000")
    if [[ "$docs_code" == "200" ]]; then
        log_success "API 文档        ✓  http://localhost:8000/docs"
    else
        log_error "API 文档        ✗  http://localhost:8000/docs (HTTP $docs_code)"
        all_ok=false
    fi

    # Promotions API (public endpoint)
    resp=$(curl -sf http://localhost:8000/api/v1/promotions 2>/dev/null || echo "FAIL")
    if echo "$resp" | grep -q '"code":0'; then
        log_success "Promotions API  ✓  http://localhost:8000/api/v1/promotions"
    else
        log_error "Promotions API  ✗  (返回异常)"
        all_ok=false
    fi

    # PostgreSQL
    if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U petal &>/dev/null; then
        log_success "PostgreSQL      ✓  localhost:5432"
    else
        log_error "PostgreSQL      ✗  localhost:5432"
        all_ok=false
    fi

    # Redis
    local pong
    pong=$(docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping 2>/dev/null || echo "FAIL")
    if [[ "$pong" == *"PONG"* ]]; then
        log_success "Redis           ✓  localhost:6379"
    else
        log_error "Redis           ✗  localhost:6379"
        all_ok=false
    fi

    # MinIO
    local minio_code
    minio_code=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:9001 2>/dev/null || echo "000")
    if [[ "$minio_code" == "200" ]]; then
        log_success "MinIO Console   ✓  http://localhost:9001"
    else
        log_error "MinIO Console   ✗  http://localhost:9001 (HTTP $minio_code)"
        all_ok=false
    fi

    # DB tables
    local table_count
    table_count=$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
        psql -U petal -d petal -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')
    if [[ "$table_count" -ge 7 ]]; then
        log_success "数据库表        ✓  ${table_count} 张表已创建"
    else
        log_error "数据库表        ✗  仅 ${table_count} 张表 (期望 >=7)"
        all_ok=false
    fi

    echo ""
    if $all_ok; then
        log_success "所有服务健康检查通过！🎉"
    else
        log_error "部分服务异常，请检查日志"
        return 1
    fi
}

# ── 运行测试 ──────────────────────────────────────────────────────────────────
run_tests() {
    log_step "运行单元测试"

    cd "$BACKEND_DIR"

    # 检查是否有 venv
    if [[ ! -d "venv" ]]; then
        log_info "创建 Python 虚拟环境..."
        python3 -m venv venv
    fi

    source venv/bin/activate

    # 安装依赖
    log_info "安装测试依赖..."
    pip install -q -r requirements.txt aiosqlite 2>&1 | tail -3

    # 运行测试
    log_info "执行 pytest..."
    python -m pytest tests/ -v --tb=short 2>&1

    local exit_code=$?
    deactivate 2>/dev/null || true

    if [[ $exit_code -eq 0 ]]; then
        log_success "所有测试通过！"
    else
        log_error "部分测试失败"
        return $exit_code
    fi
}

# ── 启动 ──────────────────────────────────────────────────────────────────────
start() {
    log_step "启动服务"
    cd "$DEPLOY_DIR"
    docker compose -f "$COMPOSE_FILE" up -d 2>&1
    wait_for_services
    log_success "所有服务已启动"
    print_summary
}

# ── 停止 ──────────────────────────────────────────────────────────────────────
stop() {
    log_step "停止服务"
    cd "$DEPLOY_DIR"
    docker compose -f "$COMPOSE_FILE" down 2>&1
    log_success "所有服务已停止"
}

# ── 重启 ──────────────────────────────────────────────────────────────────────
restart() {
    log_step "重启服务"
    cd "$DEPLOY_DIR"
    docker compose -f "$COMPOSE_FILE" down 2>&1
    docker compose -f "$COMPOSE_FILE" up -d --build 2>&1
    wait_for_services
    log_success "所有服务已重启"
    print_summary
}

# ── 查看日志 ──────────────────────────────────────────────────────────────────
show_logs() {
    cd "$DEPLOY_DIR"
    docker compose -f "$COMPOSE_FILE" logs -f --tail=100 2>&1
}

# ── 查看状态 ──────────────────────────────────────────────────────────────────
show_status() {
    log_step "服务状态"
    cd "$DEPLOY_DIR"
    docker compose -f "$COMPOSE_FILE" ps 2>&1
}

# ── 清除所有 ──────────────────────────────────────────────────────────────────
clean() {
    log_step "停止并清除所有数据"
    read -p "⚠️  这将删除所有容器和数据卷，确定？(y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        log_info "已取消"
        return
    fi
    cd "$DEPLOY_DIR"
    docker compose -f "$COMPOSE_FILE" down -v --rmi local 2>&1
    log_success "所有容器和数据已清除"
}

# ── 打印摘要 ──────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║        🌸 Petal 美妆平台 — 部署成功！                      ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}                                                            ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  📡 服务地址:                                              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ API Gateway (Nginx)  : ${CYAN}http://localhost:80${NC}             ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ Backend API          : ${CYAN}http://localhost:8000${NC}           ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ API 文档 (Swagger)   : ${CYAN}http://localhost:8000/docs${NC}     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ API 文档 (ReDoc)     : ${CYAN}http://localhost:8000/redoc${NC}    ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ MinIO Console        : ${CYAN}http://localhost:9001${NC}           ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  │   (用户名: minioadmin / 密码: minioadmin)                ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ PostgreSQL           : ${CYAN}localhost:5432${NC}                  ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  │   (数据库: petal / 用户: petal / 密码: petal_secret)     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  └─ Redis                : ${CYAN}localhost:6379${NC}                  ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}                                                            ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  📋 管理命令:                                              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ 查看状态  : ${YELLOW}./deploy.sh status${NC}                       ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ 查看日志  : ${YELLOW}./deploy.sh logs${NC}                         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ 健康检查  : ${YELLOW}./deploy.sh health${NC}                       ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ 重启服务  : ${YELLOW}./deploy.sh restart${NC}                      ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ 停止服务  : ${YELLOW}./deploy.sh stop${NC}                         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  ├─ 运行测试  : ${YELLOW}./deploy.sh test${NC}                         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  └─ 清除数据  : ${YELLOW}./deploy.sh clean${NC}                        ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}                                                            ${GREEN}║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ── 主入口 ────────────────────────────────────────────────────────────────────
main() {
    local cmd="${1:-deploy}"

    echo -e "${CYAN}"
    echo '  ____       _        _ '
    echo ' |  _ \ ___ | |_ __ _| |'
    echo ' | |_) / _ \| __/ _` | |'
    echo ' |  __/  __/| || (_| | |'
    echo ' |_|   \___| \__\__,_|_|'
    echo '                         '
    echo -e " 🌸 微信小程序美妆平台 v0.1.0${NC}"
    echo ""

    case "$cmd" in
        deploy|up)      deploy ;;
        start)          start ;;
        stop|down)      stop ;;
        restart)        restart ;;
        status|ps)      show_status ;;
        logs)           show_logs ;;
        test)           run_tests ;;
        clean|purge)    clean ;;
        health|check)   cd "$DEPLOY_DIR" && health_check ;;
        *)
            echo "用法: $0 {deploy|start|stop|restart|status|logs|test|clean|health}"
            exit 1
            ;;
    esac
}

main "$@"
