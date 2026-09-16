#!/usr/bin/env bash
# MaaWoA 启动脚本（bash / macOS / Linux / Git Bash）。
#
# 依赖缺失时自动调用 launch/setup.sh 补齐，然后从项目根目录启动 GUI。
#
# 用法：
#   launch/launch.sh              缺依赖则自动安装，然后启动
#   launch/launch.sh --no-setup   不自动安装，缺依赖直接报错退出
#   launch/launch.sh -- <args>    透传参数给 GUI
set -euo pipefail

LAUNCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${LAUNCH_DIR}/lib.sh"

AUTO_SETUP=1
PASSTHROUGH=()

usage() {
    cat <<'USAGE'
MaaWoA 启动脚本

依赖缺失时自动调用 launch/setup.sh 补齐，然后从项目根目录启动 GUI。

用法：
  launch/launch.sh              缺依赖则自动安装，然后启动
  launch/launch.sh --no-setup   不自动安装，缺依赖直接报错退出
  launch/launch.sh -- <args>    透传参数给 GUI
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-setup) AUTO_SETUP=0; shift ;;
        -h | --help)
            usage
            exit 0
            ;;
        --)
            shift
            PASSTHROUGH=("$@")
            break
            ;;
        *)
            PASSTHROUGH+=("$1")
            shift
            ;;
    esac
done

cd "$MAAWOA_PROJECT_ROOT"

# ---------------------------------------------------------------------------
# 解析 GUI 可执行文件
# ---------------------------------------------------------------------------

resolve_launcher() {
    local candidates name
    if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* || "$(uname -s)" == CYGWIN* ]]; then
        candidates=(MFAAvalonia.exe mxu.exe MFAAvalonia mxu)
    else
        candidates=(MFAAvalonia mxu MFAAvalonia.exe mxu.exe)
    fi

    for name in "${candidates[@]}"; do
        if [[ -f "${MAAWOA_PROJECT_ROOT}/${name}" ]]; then
            printf '%s\n' "${MAAWOA_PROJECT_ROOT}/${name}"
            return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

maawoa_prepare_environment

if ! maawoa_launcher_ok || ! maawoa_runtime_ok; then
    if [[ "$AUTO_SETUP" -eq 0 ]]; then
        log_error "依赖不完整，且已指定 --no-setup"
        printf '\n'
        maawoa_report_status || true
        exit 1
    fi
    log_warn "依赖不完整，先自动安装"
    "${LAUNCH_DIR}/setup.sh" || {
        log_error "依赖安装失败，无法启动"
        exit 1
    }
fi

LAUNCHER="$(resolve_launcher)" || {
    log_error "未在项目根目录找到 GUI 启动器（MFAAvalonia / mxu）"
    log_info "可执行 launch/setup.sh 重新部署"
    exit 1
}

# 防御性再确认可执行位与隔离属性（例如从压缩包解压出来的场景）
[[ -x "$LAUNCHER" ]] || chmod +x "$LAUNCHER" 2>/dev/null || true
if [[ "$(uname -s)" == "Darwin" ]] && have xattr; then
    xattr -dr com.apple.quarantine "$LAUNCHER" 2>/dev/null || true
fi

if ! maawoa_dotnet_major_ok 10; then
    log_error "未找到 .NET 10 运行时"
    log_info "可执行 launch/setup.sh 自动安装"
    exit 1
fi

log_stage "启动 $(basename "$LAUNCHER")"
log_dim "项目目录：${MAAWOA_PROJECT_ROOT}"

exec "$LAUNCHER" ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}
