#!/usr/bin/env bash
# MaaWoA 启动脚本公共库（bash）。
#
# 只应被 `source`，不要直接执行。所有函数以 `maawoa_` 前缀命名，
# 避免污染调用方的命名空间。
# shellcheck shell=bash

if [[ -n "${MAAWOA_LIB_SOURCED:-}" ]]; then
    return 0
fi
MAAWOA_LIB_SOURCED=1

# ---------------------------------------------------------------------------
# 项目根目录
# ---------------------------------------------------------------------------

# 本文件位于 <root>/launch/lib.sh，因此根目录就是它的上一级。
# 可用 MAAWOA_PROJECT_ROOT 环境变量覆盖（打包出的 .app 依赖这个能力）。
MAAWOA_LAUNCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAAWOA_PROJECT_ROOT="${MAAWOA_PROJECT_ROOT:-$(dirname "$MAAWOA_LAUNCH_DIR")}"
export MAAWOA_PROJECT_ROOT

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    MAAWOA_C_RESET=$'\033[0m'
    MAAWOA_C_DIM=$'\033[2m'
    MAAWOA_C_BOLD=$'\033[1m'
    MAAWOA_C_RED=$'\033[31m'
    MAAWOA_C_GREEN=$'\033[32m'
    MAAWOA_C_YELLOW=$'\033[33m'
    MAAWOA_C_BLUE=$'\033[34m'
else
    MAAWOA_C_RESET=""
    MAAWOA_C_DIM=""
    MAAWOA_C_BOLD=""
    MAAWOA_C_RED=""
    MAAWOA_C_GREEN=""
    MAAWOA_C_YELLOW=""
    MAAWOA_C_BLUE=""
fi

log_info() { printf '%s\n' "${MAAWOA_C_BLUE}·${MAAWOA_C_RESET} $*"; }
log_ok() { printf '%s\n' "${MAAWOA_C_GREEN}✓${MAAWOA_C_RESET} $*"; }
log_warn() { printf '%s\n' "${MAAWOA_C_YELLOW}!${MAAWOA_C_RESET} $*" >&2; }
log_error() { printf '%s\n' "${MAAWOA_C_RED}✗${MAAWOA_C_RESET} $*" >&2; }
log_dim() { printf '%s\n' "${MAAWOA_C_DIM}$*${MAAWOA_C_RESET}"; }

# 步骤序号（由 setup 维护）
MAAWOA_STEP_INDEX=0
MAAWOA_STEP_TOTAL="${MAAWOA_STEP_TOTAL:-0}"

log_stage() {
    MAAWOA_STEP_INDEX=$((MAAWOA_STEP_INDEX + 1))
    local prefix=""
    if [[ "$MAAWOA_STEP_TOTAL" -gt 0 ]]; then
        prefix="[${MAAWOA_STEP_INDEX}/${MAAWOA_STEP_TOTAL}] "
    fi
    printf '\n%s\n' "${MAAWOA_C_BOLD}${prefix}$*${MAAWOA_C_RESET}"
}

# ---------------------------------------------------------------------------
# 基础探测
# ---------------------------------------------------------------------------

have() { command -v "$1" >/dev/null 2>&1; }

# 输出 create-maa-project 使用的平台标识，例如 osx-arm64 / win-x64。
maawoa_runtime_platform() {
    local os arch
    case "$(uname -s)" in
        Darwin) os="osx" ;;
        Linux) os="linux" ;;
        MINGW* | MSYS* | CYGWIN*) os="win" ;;
        *)
            log_error "不支持的操作系统：$(uname -s)"
            return 1
            ;;
    esac

    case "$(uname -m)" in
        arm64 | aarch64) arch="arm64" ;;
        x86_64 | amd64) arch="x64" ;;
        *)
            log_error "不支持的 CPU 架构：$(uname -m)"
            return 1
            ;;
    esac

    printf '%s-%s\n' "$os" "$arch"
}

# .NET 运行时安装位置。MFAAvalonia 是 net10.0 框架依赖程序。
maawoa_dotnet_root() {
    if [[ -n "${DOTNET_ROOT:-}" && -x "${DOTNET_ROOT}/dotnet" ]]; then
        printf '%s\n' "$DOTNET_ROOT"
        return 0
    fi
    if [[ -x "${HOME}/.dotnet/dotnet" ]]; then
        printf '%s\n' "${HOME}/.dotnet"
        return 0
    fi
    if have dotnet; then
        printf '%s\n' "$(dirname "$(command -v dotnet)")"
        return 0
    fi
    return 1
}

# 检查 .NET 主版本是否满足要求（默认 10）。
maawoa_dotnet_major_ok() {
    local required="${1:-10}" root major
    root="$(maawoa_dotnet_root)" || return 1
    major="$("${root}/dotnet" --list-runtimes 2>/dev/null |
        sed -n 's/^Microsoft\.NETCore\.App \([0-9]*\)\..*/\1/p' | sort -rn | head -1)"
    [[ -n "$major" && "$major" -ge "$required" ]]
}

# ---------------------------------------------------------------------------
# 依赖状态
# ---------------------------------------------------------------------------

maawoa_runtime_dir() { printf '%s\n' "${MAAWOA_PROJECT_ROOT}/.create-maa-project/runtime"; }
maawoa_mfaa_dir() { printf '%s\n' "$(maawoa_runtime_dir)/mfaa/$(maawoa_runtime_platform)"; }
maawoa_python_dir() { printf '%s\n' "$(maawoa_runtime_dir)/python/$(maawoa_runtime_platform)"; }

maawoa_node_ok() {
    have node || return 1
    local version major minor
    version="$(node -v 2>/dev/null)" || return 1
    version="${version#v}"
    major="${version%%.*}"
    minor="$(printf '%s' "$version" | cut -d. -f2)"
    [[ "$major" =~ ^[0-9]+$ ]] || return 1
    [[ "$major" -gt 22 ]] && return 0
    [[ "$major" -eq 22 && "${minor:-0}" -ge 13 ]] && return 0
    return 1
}

maawoa_pnpm_ok() { have pnpm; }
maawoa_uv_ok() { have uv; }

maawoa_submodule_ok() {
    [[ -f "${MAAWOA_PROJECT_ROOT}/MaaCommonAssets/OCR/ppocr_v6/small/det.onnx" ]]
}

maawoa_node_deps_ok() {
    [[ -d "${MAAWOA_PROJECT_ROOT}/node_modules/@nekosu/maa-tools" ]]
}

maawoa_python_deps_ok() {
    [[ -x "${MAAWOA_PROJECT_ROOT}/.venv/bin/python" ]] ||
        [[ -x "${MAAWOA_PROJECT_ROOT}/.venv/Scripts/python.exe" ]]
}

maawoa_runtime_ok() {
    local platform native
    platform="$(maawoa_runtime_platform)" || return 1
    native="${MAAWOA_PROJECT_ROOT}/runtimes/${platform}/native"
    [[ -f "${native}/libMaaFramework.dylib" ||
        -f "${native}/libMaaFramework.so" ||
        -f "${native}/MaaFramework.dll" ]]
}

maawoa_ocr_ok() {
    [[ -f "${MAAWOA_PROJECT_ROOT}/resource/base/model/ocr/det.onnx" &&
        -f "${MAAWOA_PROJECT_ROOT}/resource/base/model/ocr/rec.onnx" &&
        -f "${MAAWOA_PROJECT_ROOT}/resource/base/model/ocr/keys.txt" ]]
}

maawoa_launcher_ok() {
    local name
    for name in MFAAvalonia mxu MFAAvalonia.exe mxu.exe; do
        [[ -f "${MAAWOA_PROJECT_ROOT}/${name}" ]] && return 0
    done
    return 1
}

# 打印依赖状态表。返回 0 表示全部就绪。
maawoa_report_status() {
    local all_ok=0

    maawoa_node_ok && log_ok "Node.js $(node -v)" || {
        log_warn "Node.js 缺失或版本过低（需要 >= 22.13）"
        all_ok=1
    }
    maawoa_pnpm_ok && log_ok "pnpm $(pnpm -v 2>/dev/null)" || {
        log_warn "pnpm 缺失（可通过 corepack 自动提供）"
        all_ok=1
    }
    maawoa_uv_ok && log_ok "uv $(uv --version 2>/dev/null | awk '{print $2}')" || {
        log_warn "uv 缺失"
        all_ok=1
    }
    maawoa_submodule_ok && log_ok "MaaCommonAssets 子模块" || {
        log_warn "MaaCommonAssets 子模块未初始化"
        all_ok=1
    }
    maawoa_node_deps_ok && log_ok "Node 依赖" || {
        log_warn "Node 依赖未安装（pnpm install）"
        all_ok=1
    }
    maawoa_python_deps_ok && log_ok "Python 依赖" || {
        log_warn "Python 依赖未安装（uv sync）"
        all_ok=1
    }
    maawoa_runtime_ok && log_ok "MaaFramework 运行时" || {
        log_warn "MaaFramework 运行时未同步（pnpm sync:runtime）"
        all_ok=1
    }
    maawoa_ocr_ok && log_ok "OCR 模型" || {
        log_warn "OCR 模型缺失"
        all_ok=1
    }
    maawoa_launcher_ok && log_ok "GUI 启动器" || {
        log_warn "GUI 启动器未就位"
        all_ok=1
    }
    maawoa_dotnet_major_ok 10 && log_ok ".NET 10 运行时" || {
        log_warn ".NET 10 运行时缺失"
        all_ok=1
    }

    return "$all_ok"
}

# 把 GUI 发行内容铺到项目根目录。
#
# 通用 GUI（MFAAvalonia / MXU）从「自身可执行文件所在目录」读取 interface.json，
# 因此必须与项目根目录的 interface.json / resource / runtimes 同级。
# --ignore-existing 保证不会覆盖 sync:runtime 生成的 runtimes/libs/plugins。
maawoa_deploy_launcher() {
    local platform="$1" src="$2"

    if [[ ! -d "$src" ]]; then
        log_error "未找到 GUI 发行目录：$src"
        return 1
    fi

    if have rsync; then
        rsync -a --ignore-existing "${src}/" "${MAAWOA_PROJECT_ROOT}/"
    else
        # 无 rsync 时退化：只补不覆盖
        (cd "$src" &&
            find . -type d -exec mkdir -p "${MAAWOA_PROJECT_ROOT}/{}" \; &&
            find . -type f -exec cp -n {} "${MAAWOA_PROJECT_ROOT}/{}" \;)
    fi

    maawoa_prepare_launcher_permissions
}

# 清除 macOS 隔离属性并补齐可执行位。
maawoa_prepare_launcher_permissions() {
    local name target
    for name in MFAAvalonia mxu; do
        target="${MAAWOA_PROJECT_ROOT}/${name}"
        [[ -e "$target" ]] || continue
        chmod +x "$target" 2>/dev/null || true
        if [[ "$(uname -s)" == "Darwin" ]] && have xattr; then
            xattr -dr com.apple.quarantine "$target" 2>/dev/null || true
            xattr -dr com.apple.provenance "$target" 2>/dev/null || true
        fi
    done

    target="${MAAWOA_PROJECT_ROOT}/libloader.dll"
    if [[ -e "$target" ]] && [[ "$(uname -s)" == "Darwin" ]] && have xattr; then
        xattr -dr com.apple.quarantine "$target" 2>/dev/null || true
    fi
}

# 图形界面（.app / Finder）启动时 PATH 往往很精简，显式补齐常用位置。
maawoa_prepare_environment() {
    local extra_paths=(
        "${HOME}/.local/bin"
        "${HOME}/.dotnet"
        "/opt/homebrew/bin"
        "/usr/local/bin"
    )
    local dir
    for dir in "${extra_paths[@]}"; do
        [[ -d "$dir" ]] || continue
        case ":${PATH}:" in
            *":${dir}:"*) ;;
            *) PATH="${dir}:${PATH}" ;;
        esac
    done
    export PATH

    local dotnet_root
    if dotnet_root="$(maawoa_dotnet_root)"; then
        export DOTNET_ROOT="$dotnet_root"
    fi
}
