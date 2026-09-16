#!/usr/bin/env bash
# MaaWoA 一键入口（bash / macOS / Linux / Git Bash）。
#
# 用法：
#   ./run.sh              安装依赖（如需）并启动应用
#   ./run.sh setup        只安装/补齐依赖
#   ./run.sh check        只检查依赖状态
#   ./run.sh -- --foo     `--` 之后的参数透传给 GUI
#
# 首次运行会下载 MaaFramework、OCR 模型、GUI 客户端与 .NET 运行时，
# 视网络情况可能需要几分钟到十几分钟。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAAWOA_PROJECT_ROOT="$ROOT"

# 注意：set -e 下无位置参数时 `shift` 会返回非零并静默终止脚本，
# 因此必须先判断 $# 再 shift。
COMMAND="${1:-launch}"
if [[ $# -gt 0 ]]; then
    shift
fi

case "$COMMAND" in
    launch | start)
        exec "${ROOT}/launch/launch.sh" "$@"
        ;;
    setup | install)
        exec "${ROOT}/launch/setup.sh" "$@"
        ;;
    check | status | doctor)
        exec "${ROOT}/launch/setup.sh" --check "$@"
        ;;
    -h | --help)
        cat <<'USAGE'
MaaWoA 一键入口

用法：
  ./run.sh              安装依赖（如需）并启动应用
  ./run.sh setup        只安装/补齐依赖
  ./run.sh check        只检查依赖状态
  ./run.sh -- --foo     `--` 之后的参数透传给 GUI
USAGE
        ;;
    *)
        # 没有识别到子命令：全部参数视为启动参数透传
        exec "${ROOT}/launch/launch.sh" "$COMMAND" "$@"
        ;;
esac
