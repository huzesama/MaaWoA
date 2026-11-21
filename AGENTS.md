# AGENTS.md

> 给在本仓库工作的编码 agent 的约定。命令与细节见 [`agent/README.md`](agent/README.md)。

## 一条最重要的原则

**改 agent 代码之前，先问：能不能用 pipeline 配置解决。**

默认答案是不改。agent 侧每一行都是长期维护成本；pipeline 配置声明式、可读、可回滚。

| 问题                       | 该在哪解决                                      |
| -------------------------- | ----------------------------------------------- |
| 节点关系 / 顺序 / 条件组合 | pipeline 的 `next` / `all_of` / `box_index`     |
| 取哪个子结果的框           | 节点的 `box_index`                              |
| 多结果取舍 / 重复框        | `filtered` + `threshold` + `order_by` + `index` |
| 语义真的表达不出来         | ← 才改代码                                      |

> 一句话：**节点选错了就改节点配置，别在 custom 识别/动作里加特判去兜底。**
>
> 完整判据 + 2026-11-21 `inverseDiff` 的教训：`agent/README.md` 的「零」章节。

## 给 custom 选输入节点：必须能产出多个 filtered

`inverseDiff` 这类「吃别的节点识别结果」的 custom，`filter_node_name` 必须指向**本身就能产出多个 filtered 结果的节点**。

| 节点形态                                        | filtered 数量                        |
| ----------------------------------------------- | ------------------------------------ |
| `TemplateMatch` / `NeuralNetworkDetect` / `OCR` | N 个 ✅                              |
| `ColorMatch` + `connected: true`                | N 个（按连通域拆开）✅               |
| **`ColorMatch` + `connected: false`**           | **1 个**（所有色块并成一个大框）❌   |
| `rectOffset` + `filter: true`                   | N 个 ✅                              |
| 靠 `roi: "<别的节点>"` 引用                     | **1 个**（跨识别任务只剩整体 box）❌ |
| `And` / `Or` 组合节点                           | **1 个**（box_index 选中的那个）❌   |

源码依据：

```cpp
// Vision/ColorMatcher.cpp:45
ResultsVec results = param_.connected
    ? count_non_zero_with_connected(bin, roi_.tl())   // 连通域 → N 个
    : count_non_zero(bin, roi_.tl());                 // 整体   → 1 个
```

### 想拿多结果但源节点给不出时

**不要再写新 custom**，包一层 `rectOffset` 即可：

```jsonc
"__xxxExcludeZone__": {
    "recognition": { "type": "Custom", "param": {
        "custom_recognition": "rectOffset",
        "custom_recognition_param": {
            "node_name": "<真正产多结果的节点>",
            "filter": true,          // ★ 必须 true，否则只给 1 个
            "offset": [0, 0, 0, 0]
        }
    }}
}
```

> ⚠️ 不要为了拿多结果去改 `And` 链里节点的 `connected` 或顺序 ——
> `And` 的 `box_index` 和兄弟依赖要求严格顺序，改了就破坏语义。

## 校验

```powershell
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync pyright
node tools/validate-schema.mjs
```
