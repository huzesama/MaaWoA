# agent 目录说明

> 本文件说明 `agent/utils/` 工具库的用法，以及 `agent/custom/` 的编写规范。

---

## 一、启动流程

```
客户端（MFAA / MXU / MaaPiCli）
   └─ python agent/main.py <socket_id>
        ├─ main.py            校验 Python 3.13、切到项目根、把 agent/ 加进 sys.path
        ├─ maafw_paths.py     定位客户端那份 MaaFramework 原生库 → 设 MAAFW_BINARY_PATH
        ├─ agent_runtime.py   configure_runtime_paths() → custom.register_all() → AgentServer.start_up()
        └─ custom/            注册自定义识别 / 动作 / sink
```

> ⚠️ **硬性顺序**：`maafw_paths` 必须在任何 `import maa` 之前运行。
> `utils` 包在被导入时就会连带 `import maa`，而 `maa` 在导入时就读 `MAAFW_BINARY_PATH` 把库目录定死。
> 所以 `maafw_paths.py` 放在 `agent/` **顶层**，故意不放进 `utils/`。

---

## 二、目录结构

```
agent/
├── main.py                入口（Python 版本校验 / chdir / sys.path）
├── maafw_paths.py         原生库定位（必须最先执行）
├── agent_runtime.py       启动 AgentServer、注册 custom、打印 PI 环境
├── utils/                 工具库 ← 下面逐个说明
│   ├── logger.py          日志（loguru 优先，stdlib 回退）
│   ├── params.py          参数解析 / 类型收敛 / 常量覆盖
│   ├── maa_types.py       识别结果类型收窄（TypeGuard）
│   ├── pienv.py           Project Interface 环境变量
│   └── runtime_paths.py   项目路径常量
└── custom/
    ├── action/            自定义动作（CustomAction）
    ├── reco/              自定义识别（CustomRecognition）
    └── sink/              自定义 sink（当前注册表为空）
```

---

## 三、utils 工具库

### 3.1 `utils/logger.py` —— 日志

```python
from utils import logger
```

`logger` 是一个**已经初始化好的** loguru logger（没装 loguru 时自动回退到标准 logging）。

| 项         | 值                                                    |
| ---------- | ----------------------------------------------------- |
| 控制台等级 | `INFO`（可用 `change_console_level("DEBUG")` 动态改） |
| 文件 sink  | `debug/custom/YYYY-MM-DD.log`，**固定 DEBUG 级**      |
| 文件保留   | 2 周，每晚 00:00 轮转，自动 zip 压缩                  |
| 占位符风格 | **`{}`**（loguru 风格），不是 f-string、不是 `%s`     |

```python
logger.info("cache {} at {} override: {}", roi_name, box, override)   # ✅
logger.info(f"cache {roi_name}")                                       # ❌ 不要用 f-string
logger.info("cache %s", roi_name)                                      # ❌ 不要用 % 风格
```

**客户端差异会被自动处理**，你不需要关心：

| 客户端      | 控制台渲染                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------ |
| MFAAvalonia | 每行自动加 `info:` / `err:` 前缀（它逐行解析，无前缀的行会被丢弃）                         |
| MXU         | 每行包成 `<span style="color:...">`，HTML 转义后只还原 `<font color="#RRGGBB">` 白名单标记 |
| 其它        | ANSI 颜色                                                                                  |

**多行日志**（`\n`）会被逐行处理，不用手动拆。

导出：`setup_logger`、`change_console_level`、`logger`

---

### 3.2 `utils/params.py` —— 参数解析

#### `parse_params(raw, *required_keys) -> dict`

把 MaaFW 传来的 `custom_action_param` / `custom_recognition_param` 字符串解析成 dict。

```python
from utils.params import parse_params

try:
    params = parse_params(argv.custom_recognition_param, "roi_name", "model", "expected")
except ValueError as error:
    logger.error("MyReco: {}", error)
    return None

roi_name = params["roi_name"]
```

| 输入                            | 行为                                                                     |
| ------------------------------- | ------------------------------------------------------------------------ |
| `None` / `""` / 字符串 `"null"` | 返回 `{}`（MaaFW 在节点省略 `custom_*_param` 时传的就是字面量 `"null"`） |
| 非法 JSON                       | 抛 `ValueError`                                                          |
| 不是对象                        | 抛 `ValueError`                                                          |
| 缺 `required_keys`              | 抛 `ValueError`                                                          |

#### `coerce_like(value, default, key) -> Any`

把 JSON 反序列化出来的值**收敛成默认值的形状**，用于参数覆盖。

| `default` 类型   | 接受的 `value`                             | 说明                                       |
| ---------------- | ------------------------------------------ | ------------------------------------------ |
| `tuple` / `list` | list / tuple，长度必须一致、元素必须是数字 | 返回和 default 相同类型（ROI 必须是 4 个） |
| `bool`           | 只接受 `bool`                              | 先于 int 判断（`bool` 是 `int` 子类）      |
| `int` / `float`  | 数字（排除 bool）                          | 转成对应类型                               |
| `str`            | 只接受 `str`                               |                                            |
| 其它             | 要求类型完全一致                           |                                            |

形状或类型不符时抛 `ValueError`。

#### `ParamOverrideMixin`

给 CustomRecognition 用：用 JSON 参数**覆盖类常量**，实现「pipeline 调参 + Python 兜底默认值」。

```python
from utils.params import ParamOverrideMixin, parse_params

class MyReco(ParamOverrideMixin, CustomRecognition):
    SAT_MIN = 100               # 类常量 = 默认值
    SAT_MAX = 255
    OVERRIDABLE = frozenset()   # 允许被覆盖的常量名（大写）

    def __init__(self) -> None:
        self.OVERRIDABLE = frozenset({"SAT_MIN", "SAT_MAX"})

    def analyze(self, context, argv):
        params = parse_params(argv.custom_recognition_param)
        self.apply_param_overrides(params)   # 每次进入先清空旧覆盖，再套新参数
```

规则：

- JSON 键名 = 类常量名的小写（`sat_min` → `SAT_MIN`）
- 不在 `OVERRIDABLE` 里的键：打 warning 并忽略
- 值非法：打 error 并回落到默认值
- 每次 `apply_param_overrides` 先清空上一次的实例覆盖，避免跨节点串味
- **线程安全**：MaaFW 对同一个 Tasker 的回调是串行的
- 特殊键 `query` 会被跳过

导出：`parse_params`、`coerce_like`、`ParamOverrideMixin`

---

### 3.3 `utils/maa_types.py` —— 识别结果收窄

MaaFW 的 `RecognitionDetail` 字段都是可选的，裸用要写一堆 `if detail and detail.hit and detail.box`。本模块用 `TypeGuard` 把这些检查收窄。

| 函数                           | 返回                           | 说明                                                     |
| ------------------------------ | ------------------------------ | -------------------------------------------------------- |
| `is_hit(detail)`               | `TypeGuard`                    | 有 hit 且有 box 时 True（收窄成 `HitRecognitionDetail`） |
| `require_hit(detail)`          | `HitRecognitionDetail`         | 不满足时抛 `ValueError`                                  |
| `best_result_as(detail, T)`    | `T` 或 `None`                  | 最佳结果且类型匹配                                       |
| `results_as(detail, T)`        | `list[T]`                      | `filtered_results` 里类型匹配的                          |
| `all_results_as(detail, T)`    | `list[T]`                      | `all_results` 里类型匹配的                               |
| `ocr_result(detail)`           | `OCRResult` 或 `None`          | `best_result_as(detail, OCRResult)`                      |
| `require_ocr_result(detail)`   | `OCRResult`                    | 没有 OCR 结果时抛 `ValueError`                           |
| `ocr_text(detail, default="")` | `str`                          | 最佳 OCR 的文本                                          |
| `ocr_results(detail)`          | `list[OCRResult]`              | 全部 OCR 结果                                            |
| `recognition_results(detail)`  | `list[RecognitionResult]`      | 命中时的 `filtered_results`                              |
| `has_box_result(result)`       | `TypeGuard`                    | 是否带 box                                               |
| `boxed_results(detail)`        | `list[BoxedRecognitionResult]` | 过滤出带 box 的结果                                      |
| `best_box(detail)`             | `Rect` 或 `None`               | 最佳结果的 box                                           |

```python
from utils.maa_types import is_hit, ocr_text

detail = context.run_recognition("__crewUsedCompareOCR__", image, pipeline_override={...})
if not is_hit(detail):
    return None
text = ocr_text(detail, "?/?")
box = detail.box            # 已被收窄，类型检查器知道它非 None
```

---

### 3.4 `utils/pienv.py` —— Project Interface 环境变量

读取客户端注入的 `PI_*` 环境变量。**懒初始化**：第一次访问时才读，之后缓存；`init(force=True)` 可强制重读。

| 函数                                   | 返回                   | 对应环境变量              |
| -------------------------------------- | ---------------------- | ------------------------- |
| `interface_version()`                  | `str`                  | `PI_INTERFACE_VERSION`    |
| `client_name()`                        | `str`                  | `PI_CLIENT_NAME`          |
| `client_version()`                     | `str`                  | `PI_CLIENT_VERSION`       |
| `client_language()`                    | `str`                  | `PI_CLIENT_LANGUAGE`      |
| `client_maafw_version()`               | `str`                  | `PI_CLIENT_MAAFW_VERSION` |
| `project_version()`                    | `str`                  | `PI_VERSION`              |
| `controller()`                         | `Controller` 或 `None` | `PI_CONTROLLER`（JSON）   |
| `resource()`                           | `Resource` 或 `None`   | `PI_RESOURCE`（JSON）     |
| `controller_type()`                    | `str`                  | 如 `"Adb"` / `"Win32"`    |
| `controller_name()`                    | `str`                  |                           |
| `resource_name()` / `resource_label()` | `str`                  |                           |
| `resource_paths()`                     | `list[str]`            | 当前资源的 path 列表      |

`Controller` / `Resource` 是冻结 dataclass，结构对应 interface.json 的 `controller[]` / `resource[]`。

```python
from utils import pienv

if pienv.controller_type() == "Adb":
    logger.debug("当前跑在 Android 上，资源 {}", pienv.resource_paths())
```

JSON 解析失败只打 warning 并返回 `None`，不会抛异常 —— 所以调用方要判空。

特殊依赖：`logger.py` 用它区分客户端（MFAA / MXU）来决定日志渲染方式。

---

### 3.5 `utils/runtime_paths.py` —— 运行时路径

```python
from utils.runtime_paths import get_runtime_paths

paths = get_runtime_paths()
paths.project_root   # 项目根（默认 agent/ 的上两级）
paths.agent_dir      # <root>/agent
paths.work_root      # 实际工作目录（= 客户端 cwd，可能不是 project_root）
paths.config_dir     # <work_root>/config
paths.resource_dir   # <work_root>/resource
paths.debug_dir      # <work_root>/debug
paths.interface_file # <project_root>/interface.json
```

`agent_runtime.py` 启动时已经调用过 `configure_runtime_paths(project_root=..., work_root=os.getcwd())`，所以 **custom 代码里直接用 `get_runtime_paths()` 即可**，不要再算路径。

> `project_root` 和 `work_root` 可能不同：发行包里 agent 在 `<install>/agent/`，而 cwd 是安装目录。

---

## 四、编写 custom 的规范

### 4.1 注册方式

三个注册表，**模块名必须登记，否则不会加载**：

| 目录             | 注册表文件                                             | 装饰器                                    |
| ---------------- | ------------------------------------------------------ | ----------------------------------------- |
| `custom/reco/`   | `custom/reco/__init__.py` → `RECO_MODULES`             | `@AgentServer.custom_recognition("名字")` |
| `custom/action/` | `custom/action/__init__.py` → `ACTION_MODULES`         | `@AgentServer.custom_action("名字")`      |
| `custom/sink/`   | `custom/sink/__init__.py` → `SINK_MODULES`（当前为空） | sink 装饰器                               |

```python
# custom/reco/__init__.py
RECO_MODULES = (
    "general",
    ...
    "NewReco",        # ← 新增文件后必须加进来
)
```

### 4.2 命名规范

| 对象   | 规范                 | 例                   |
| ------ | -------------------- | -------------------- |
| 文件名 | `snake_case.py`      | `crewUsedCompare.py` |
| 类名   | `PascalCase`         | `CrewUsedCompare`    |
| 注册名 | 与文件名一致（推荐） | `"crewUsedCompare"`  |

现有代码里两种注册名风格都存在（`"roiManager"` 与 `"ExampleRecognition"`），**建议统一成与文件名一致**，方便从 pipeline 反查文件。

### 4.3 回调规范（重要）

| 规则                                     | 原因                                                                                 |
| ---------------------------------------- | ------------------------------------------------------------------------------------ |
| **不要抛异常**                           | 异常会打断整条流水线；统一 `return None`（识别）/ `RunResult(success=False)`（动作） |
| **参数解析必须 try/except `ValueError`** | `parse_params` 会抛                                                                  |
| **日志用 `{}` 占位**                     | loguru 风格                                                                          |
| **失败要打日志**                         | `logger.error("节点名: 原因")`，否则排查时完全没有线索                               |
| **返回 box 用 `RectType`**               | `CustomRecognition.AnalyzeResult(box=(x, y, w, h))`                                  |

标准骨架：

```python
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_recognition import CustomRecognition
from utils import logger
from utils.params import parse_params


@AgentServer.custom_recognition("myReco")
class MyReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        try:
            params = parse_params(argv.custom_recognition_param, "threshold")
        except ValueError as error:
            logger.error("myReco: {}", error)
            return None

        try:
            # ... 实际逻辑 ...
            return CustomRecognition.AnalyzeResult(box=(0, 0, 10, 10), detail={"ok": True})
        except Exception as error:          # 兜底：绝不让异常穿出去
            logger.error("myReco: unexpected {}", error)
            return None
```

### 4.4 `general.py` 的定位

| 文件                       | 内容                                   | 建议                                                                                             |
| -------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `custom/reco/general.py`   | 只有一个 `ExampleRecognition` **模板** | 当前未在 pipeline 使用；可作为写法参考，不需要可删（记得同步删 `RECO_MODULES` 里的 `"general"`） |
| `custom/action/general.py` | **4 个通用工具动作**                   | **建议保留** —— 见下表                                                                           |

`custom/action/general.py` 的内置动作：

| 注册名         | 作用                                                     | `custom_action_param`                                           |
| -------------- | -------------------------------------------------------- | --------------------------------------------------------------- |
| `DisableNode`  | 运行时禁用一个节点                                       | `{"node_name": "NodeName"}`                                     |
| `NodeOverride` | 把整个 override 对象透传给 `context.override_pipeline()` | `{"NodeName": {"enabled": false}}`                              |
| `ResetCount`   | 清空一个或多个节点的命中计数                             | `{"nodes": ["A","B"], "strict": false}`                         |
| `SubTask`      | 从动作节点里按顺序跑子任务                               | `{"sub": ["TaskA","TaskB"], "continue": false, "strict": true}` |

这些都是**通用工具**，虽然当前 pipeline 没有引用，但随时可以在 JSON 里用：

```jsonc
"myNode": {
    "action": "Custom",
    "custom_action": "DisableNode",
    "custom_action_param": { "node_name": "someNode" }
}
```

---

## 五、新增一个 CustomRecognition 的完整步骤

1. 在 `agent/custom/reco/` 下新建 `myNewReco.py`，按 4.3 的骨架写
2. 在 `agent/custom/reco/__init__.py` 的 `RECO_MODULES` 里加 `"myNewReco"`（**漏了这步不会生效**）
3. 在 pipeline JSON 里引用：

```jsonc
"myNode": {
    "recognition": {
        "type": "Custom",
        "param": {
            "custom_recognition": "myNewReco",
            "custom_recognition_param": { "threshold": 0.8 }
        }
    }
}
```

4. 跑校验：

```powershell
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync pyright
node tools/validate-schema.mjs
```

**新增 CustomAction 同理**，改 `ACTION_MODULES`。

---

## 六、常见陷阱

| 陷阱                                         | 说明                                                                                                     |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 忘了登记 `RECO_MODULES`                      | 文件写了但 MaaFW 找不到该识别名，pipeline 直接不命中，**没有任何报错**                                   |
| 在 `import maa` 之后再设 `MAAFW_BINARY_PATH` | 无效，库目录已定死                                                                                       |
| 用 f-string 打日志                           | loguru 下能跑，但丢失结构化字段；统一 `{}`                                                               |
| 省略 `custom_*_param` 后直接 `json.loads`    | MaaFW 传的是字面量 `"null"`，`json.loads("null")` 返回 `None`，后续取键会 `TypeError`。用 `parse_params` |
| 在回调里抛异常                               | 打断流水线；请 `return None` / `success=False`                                                           |
| 以为 `debug(...)` 会出现在 GUI               | 不会。控制台是 INFO 级，`debug` 只进 `debug/custom/*.log`                                                |
| `pienv` 拿不到值                             | 环境变量是客户端注入的；从 IDE 直接跑 `main.py` 时不存在，判空即可                                       |
| `configure_runtime_paths` 被重复调用         | 会覆盖全局路径；除了启动阶段，业务代码不要调                                                             |

---

## 七、相关文件

- 原生库定位细节：`agent/maafw_paths.py` 顶部 docstring
- 版本号为什么不用 pip 元数据：`agent/agent_runtime.py` → `_log_maafw_version()` 的 docstring
- 日志渲染为什么要区分客户端：`agent/utils/logger.py` 中间的注释块
