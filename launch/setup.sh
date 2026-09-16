#!/usr/bin/env bash
# MaaWoA 依赖一键安装（bash / macOS / Linux / Git Bash）。
#
# 幂等：已就绪的步骤自动跳过，可反复执行。
#
# 用法：
#   launch/setup.sh              安装/补齐全部依赖
#   launch/setup.sh --check      只检查状态，不做任何改动
#   launch/setup.sh --yes        全部自动确认（非交互）
#   launch/setup.sh --force      忽略就绪标记，强制重跑
set -euo pipefail

LAUNCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${LAUNCH_DIR}/lib.sh"

# corepack 首次使用 packageManager 指定的 pnpm 版本时会询问是否下载，
# 关闭询问让安装过程完全非交互。
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

ASSUME_YES=0
CHECK_ONLY=0
FORCE=0

usage() {
    cat <<'USAGE'
MaaWoA 依赖一键安装（幂等，可反复执行）

用法：
  launch/setup.sh              安装/补齐全部依赖
  launch/setup.sh --check      只检查状态，不做任何改动
  launch/setup.sh --yes        全部自动确认（非交互）
  launch/setup.sh --force      忽略就绪标记，强制重跑
USAGE
}

for arg in "$@"; do
    case "$arg" in
        -y | --yes) ASSUME_YES=1 ;;
        -c | --check) CHECK_ONLY=1 ;;
        -f | --force) FORCE=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            log_error "未知参数：$arg"
            exit 2
            ;;
    esac
done

cd "$MAAWOA_PROJECT_ROOT"

# ---------------------------------------------------------------------------
# 交互辅助
# ---------------------------------------------------------------------------

confirm() {
    local prompt="$1"
    if [[ "$ASSUME_YES" -eq 1 ]]; then
        log_info "${prompt}（--yes 自动确认）"
        return 0
    fi
    if [[ ! -t 0 ]]; then
        log_warn "${prompt} —— 非交互环境，已跳过"
        return 1
    fi
    local reply
    read -r -p "$(printf '%s [y/N] ' "$prompt")" reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

# 包装子步骤，失败时给出可读上下文，而不是裸的 set -e 退出。
run_step() {
    local description="$1"
    shift
    if ! "$@"; then
        log_error "${description} 失败"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# 各依赖的安装动作
# ---------------------------------------------------------------------------

install_node() {
    if [[ "$(uname -s)" == "Darwin" ]]; then
        have brew || {
            log_error "未找到 Homebrew，无法自动安装 Node.js"
            log_info "请手动安装 Node.js >= 22.13：https://nodejs.org/"
            return 1
        }
        confirm "使用 Homebrew 安装 Node.js 22？" || return 1
        brew install node@22
        return 0
    fi

    # Linux：优先用发行版包管理器
    if have apt-get; then
        confirm "使用 apt 安装 Node.js？" || return 1
        curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
        sudo apt-get install -y nodejs
    elif have dnf; then
        confirm "使用 dnf 安装 Node.js 22？" || return 1
        sudo dnf install -y nodejs22
    else
        log_error "未找到可用的包管理器，请手动安装 Node.js >= 22.13"
        return 1
    fi
}

install_pnpm() {
    if have corepack; then
        log_info "通过 corepack 启用 pnpm ..."
        corepack enable pnpm 2>/dev/null || corepack prepare --activate || true
    fi
    if ! maawoa_pnpm_ok; then
        log_error "pnpm 不可用"
        log_info "请手动安装：npm install -g pnpm"
        return 1
    fi
}

install_uv() {
    confirm "通过官方脚本安装 uv？" || return 1
    log_info "下载并安装 uv ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # 官方脚本装到 ~/.local/bin，当前 shell 的 PATH 尚未刷新
    export PATH="${HOME}/.local/bin:${PATH}"
    maawoa_uv_ok || {
        log_error "uv 安装后仍不可用，请重开终端后再试"
        return 1
    }
}

init_submodule() {
    git submodule update --init --depth 1 MaaCommonAssets
}

install_node_deps() {
    pnpm install
}

install_python_deps() {
    # --frozen：只按 uv.lock 安装，避免被本地 PyPI 镜像配置改写锁文件
    uv sync --frozen
}

sync_runtime() {
    local platform
    platform="$(maawoa_runtime_platform)"
    CREATE_MAA_PROJECT_RUNTIME_PLATFORM="$platform" pnpm sync:runtime
}

install_dotnet() {
    local install_dir="${HOME}/.dotnet"
    local tmp_script
    tmp_script="$(mktemp -t dotnet-install.XXXXXX.sh)"

    log_info "下载 dotnet-install.sh ..."
    curl -sSL --retry 5 --retry-all-errors -o "$tmp_script" https://dot.net/v1/dotnet-install.sh
    chmod +x "$tmp_script"
    log_info "安装 .NET 10 运行时到 ${install_dir} ..."
    "$tmp_script" --channel 10.0 --runtime dotnet --install-dir "$install_dir"
    rm -f "$tmp_script"

    export DOTNET_ROOT="$install_dir"
    export PATH="${PATH}:${install_dir}"
}

deploy_launcher() {
    local platform
    platform="$(maawoa_runtime_platform)"
    maawoa_deploy_launcher "$platform" "$(maawoa_mfaa_dir)"
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

if [[ "$CHECK_ONLY" -eq 1 ]]; then
    printf '%s\n' "${MAAWOA_C_BOLD}MaaWoA 依赖状态${MAAWOA_C_RESET}"
    log_dim "项目目录：${MAAWOA_PROJECT_ROOT}"
    log_dim "平台标识：$(maawoa_runtime_platform)"
    printf '\n'
    if maawoa_report_status; then
        printf '\n'
        log_ok "全部依赖已就绪"
        exit 0
    fi
    printf '\n'
    log_warn "存在缺失依赖，执行 launch/setup.sh 补齐"
    exit 1
fi

# 标题不占用步骤编号，7 个安装阶段 + 校验 = 8
MAAWOA_STEP_TOTAL=8

printf '%s\n' "${MAAWOA_C_BOLD}MaaWoA 依赖安装${MAAWOA_C_RESET}"
log_dim "项目目录：${MAAWOA_PROJECT_ROOT}"
log_dim "平台标识：$(maawoa_runtime_platform)"

# 1. 基础工具 --------------------------------------------------------------
log_stage "检查基础工具"
if ! maawoa_node_ok; then
    if have node; then
        log_warn "Node.js $(node -v) 版本过低，需要 >= 22.13"
    else
        log_warn "未找到 Node.js"
    fi
    install_node
fi
log_ok "Node.js $(node -v)"

if ! maawoa_pnpm_ok; then
    log_warn "未找到 pnpm"
    install_pnpm
fi
log_ok "pnpm $(pnpm -v)"

if ! maawoa_uv_ok; then
    log_warn "未找到 uv"
    install_uv
fi
log_ok "uv $(uv --version | awk '{print $2}')"

# 2. 子模块 ----------------------------------------------------------------
log_stage "初始化 MaaCommonAssets 子模块"
if [[ "$FORCE" -eq 0 ]] && maawoa_submodule_ok; then
    log_dim "已初始化，跳过"
else
    run_step "子模块初始化" init_submodule
fi
log_ok "OCR 资源就位"

# 3. Node 依赖 -------------------------------------------------------------
log_stage "安装 Node 依赖"
if [[ "$FORCE" -eq 0 ]] && maawoa_node_deps_ok; then
    log_dim "已安装，跳过"
else
    run_step "pnpm install" install_node_deps
fi
log_ok "Node 依赖就绪"

# 4. Python 依赖 -----------------------------------------------------------
log_stage "安装 Python 依赖"
if [[ "$FORCE" -eq 0 ]] && maawoa_python_deps_ok; then
    log_dim "已安装，跳过"
else
    run_step "uv sync" install_python_deps
fi
log_ok "Python 依赖就绪"

# 5. 运行时资源 ------------------------------------------------------------
log_stage "同步 MaaFramework / OCR / GUI 运行时"
log_dim "首次执行需要下载较多内容，请耐心等待"
if [[ "$FORCE" -eq 0 ]] && maawoa_runtime_ok && maawoa_ocr_ok; then
    log_dim "已同步，跳过"
else
    run_step "pnpm sync:runtime" sync_runtime
fi
log_ok "运行时资源就绪"

# 6. .NET 运行时 -----------------------------------------------------------
log_stage "检查 .NET 10 运行时"
if [[ "$FORCE" -eq 0 ]] && maawoa_dotnet_major_ok 10; then
    log_dim "已安装，跳过"
else
    log_warn ".NET 10 运行时缺失，MFAAvalonia 需要它"
    run_step ".NET 运行时安装" install_dotnet
fi
log_ok ".NET 运行时就绪"

# 7. 部署 GUI --------------------------------------------------------------
log_stage "部署 GUI 启动器"
if [[ "$FORCE" -eq 0 ]] && maawoa_launcher_ok; then
    log_dim "已部署，刷新权限"
    maawoa_prepare_launcher_permissions
else
    run_step "启动器部署" deploy_launcher
fi
log_ok "启动器就绪"

# 8. 校验 ------------------------------------------------------------------
log_stage "依赖校验"
if maawoa_report_status; then
    printf '\n'
    log_ok "全部依赖已就绪"
    log_dim "启动应用：./run.sh"
    exit 0
fi

printf '\n'
log_error "仍有依赖缺失，请检查上方输出"
exit 1
