<#
.SYNOPSIS
    MaaWoA 一键入口（PowerShell / Windows）。

.DESCRIPTION
    首次运行会下载 MaaFramework、OCR 模型、GUI 客户端与 .NET 运行时，
    视网络情况可能需要几分钟到十几分钟。

.EXAMPLE
    ./run.ps1
    安装依赖（如需）并启动应用

.EXAMPLE
    ./run.ps1 setup
    只安装/补齐依赖

.EXAMPLE
    ./run.ps1 check
    只检查依赖状态

.EXAMPLE
    ./run.ps1 launch -- --foo bar
    ``--`` 之后的参数透传给 GUI
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Command = 'launch',
    [Parameter(ValueFromRemainingArguments)][string[]]$Rest
)

$env:MAAWOA_PROJECT_ROOT = $PSScriptRoot

# PowerShell 陷阱：`$x = if (...) { @() }` 会把空数组展开成 $null，
# 之后 @x 展开传参就会多出一个 $null 位置参数。必须显式初始化为空数组。
$arguments = @()
if ($Rest) { $arguments = @($Rest) }

switch -Regex ($Command) {
    '^(launch|start)$' {
        & "$PSScriptRoot/launch/launch.ps1" @arguments
        exit $LASTEXITCODE
    }
    '^(setup|install)$' {
        & "$PSScriptRoot/launch/setup.ps1" @arguments
        exit $LASTEXITCODE
    }
    '^(check|status|doctor)$' {
        & "$PSScriptRoot/launch/setup.ps1" -Check @arguments
        exit $LASTEXITCODE
    }
    default {
        # 未知子命令整体透传给启动脚本，方便 `./run.ps1 -?`
        & "$PSScriptRoot/launch/launch.ps1" @(@($Command) + $arguments)
        exit $LASTEXITCODE
    }
}
