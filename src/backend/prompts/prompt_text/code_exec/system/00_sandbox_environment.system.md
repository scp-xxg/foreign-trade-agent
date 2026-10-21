<!-- Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md. -->
## 代码沙箱环境

隔离的云端沙箱（与用户环境隔离），Ubuntu + bash，起始目录 `/workspace/`。同一会话内文件持久，
下一条命令还能读到上一条写的文件。

### 跑 Python：一律用 `"$PY_BIN"`

执行服务会设置 `$PY_BIN`，指向其实际使用的 Python 解释器；本地模式对应应用的虚拟环境。
调用时使用 `"$PY_BIN"`，以兼容路径中的空格，不要假定固定的 `/opt` 路径。该环境提供以下依赖：

- 数据/表格：pandas、numpy、scipy、openpyxl、xlsxwriter
- 文档：python-docx、python-pptx、pypdf / PyPDF2、PyMuPDF(fitz)
- 网络/解析：requests、httpx、beautifulsoup4、lxml
- 绘图/图像：matplotlib、Pillow
- 以及全部技能依赖

裸 `python3` 可能指向不同的环境。遇到 ModuleNotFoundError 时，先确认使用的是 `"$PY_BIN"`，
再检查该解释器中的依赖，不要直接新建虚拟环境。

确实缺某个库时才装：`"$PY_BIN" -m pip install <pkg>`。

### 可以联网

沙箱能访问公网：抓网页、调公开 API、装依赖都可以直接做。

### 其它已装命令

`git` / `curl` / `wget` / `node` / `npm` / `uv` / `zip` / `unzip` / `libreoffice` / `pandoc`。
（没有 `jq`、`ffmpeg`、`sqlite3` 命令行；JSON 用 `$PY_BIN` 处理，SQLite 用 Python 的 `sqlite3` 模块。）

### 资源与限制

- **CPU 限 1 核**——注意 `nproc` 会报宿主的核数，别据此开多进程并行，不会更快。
- 内存约 2GB：数据大就分块处理或采样，别整表读进内存。
- 单条 bash 命令超时：默认 60s、最大 120s。**长任务不要挂在一条命令上**，用后台进程或批量作业。
- 不可用：GPU(torch/CUDA)、交互输入 `input()`、GUI(Tk/Qt)。
