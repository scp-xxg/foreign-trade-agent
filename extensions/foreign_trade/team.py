"""Prepare and run this checkout's foreign-trade demo (Linux/WSL, Python 3.11+).

    python3.11 extensions/foreign_trade/team.py setup
    .venv/bin/python extensions/foreign_trade/team.py init
    .venv/bin/python extensions/foreign_trade/team.py start

Each teammate creates a local account and configures their own model in the web
UI. No database, password, API key, or model configuration is copied from others.
Use --app-home PATH on every command to choose a different local data directory.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VENV = ROOT / ".venv"
PYTHON = VENV / "bin/python"
FRONTEND = ROOT / "src/frontend"
DEFAULT_HOME = Path.home() / ".foreign-trade-agent"


def runtime_env(home: Path, port: int = 3001) -> dict[str, str]:
    """Pin all local data/services; never inherit another project's data root."""
    env = os.environ.copy()
    env.update({
        "HUGAGENT_HOME": str(home), "HUGAGENT_CAPS_ROOT": str(home),
        "HUGAGENT_SKIP_ENV_FILES": "1", "DEPLOY_PROFILE": "local",
        "JX_EDITION": "ce", "BRAND_PRODUCT_NAME": "HugAgentOS",
        "DATABASE_URL": "sqlite:///" + str(home / "data.db"),
        "REDIS_URL": "", "SESSION_STORE": "memory", "AUTH_MODE": "session",
        "SSO_LOGIN_MODE": "local", "LOCAL_AUTH_ENABLED": "true",
        "STORAGE_TYPE": "local", "STORAGE_PATH": str(home / "storage"),
        "SCRIPT_RUNNER_WORKSPACE": str(home / "workspace"),
        "SANDBOX_SKILLS_DIR": str(home / "workspace/skills"),
        "SANDBOX_PROVIDER": "script_runner", "SANDBOX_RUNNER_URL": "http://127.0.0.1:8900",
        "SANDBOX_TOOLS_ENABLED": "true", "MCP_HOST": "127.0.0.1",
        "HUGAGENT_BOOTSTRAP_DEFAULT_PLUGINS": "1",
        "LOG_FILE_PATH": str(home / "logs/backend.log"),
        "MILVUS_URL": str(home / "milvus.db"),
        "LOCAL_PRIVATE_KB_ENABLED": "true",
        "MEM0_ENABLED": "false",  # Optional vector memory needs its own model/runtime.
        "NODE_PATH": str(home / "node/node_modules"),
        "PLAYWRIGHT_BROWSERS_PATH": str(home / "node/browsers"),
        "JX_FONT_DIR": str(home / "fonts"),
        "SITE_TEMPLATE_HOME": str(home / "site-template"),
        "SITE_TEMPLATE_DIR": str(home / "site-template/react-vite"),
        "SITE_NODE_BASE": str(home / "workspace/.site-node"),
        "FRONTEND_DIST_DIR": str(FRONTEND / "dist"),
        "BACKEND_INTERNAL_URL": f"http://127.0.0.1:{port}", "BACKEND_PORT": str(port), "PORT": str(port),
        "PATH": str(VENV / "bin") + os.pathsep + env.get("PATH", ""),
        "PYTHONPATH": str(ROOT / "src/backend"),
        "PYTHONUNBUFFERED": "1",
    })
    for key in ("NO_PROXY", "no_proxy"):
        entries = [value.strip() for value in env.get(key, "").split(",") if value.strip()]
        env[key] = ",".join(dict.fromkeys([*entries, "127.0.0.1", "localhost", "::1"]))
    return env


def run(command: list[str | Path], *, env: dict[str, str], dry_run: bool = False) -> None:
    command = [str(value) for value in command]
    print("+ " + shlex.join(command), flush=True)
    if not dry_run:
        subprocess.run(command, cwd=ROOT, env=env, check=True)


def node_supported(version: str) -> bool:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    if match is None:
        return False
    major, minor, _ = map(int, match.groups())
    return (major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major > 22


def prerequisite_check() -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError("需要 Python 3.11+，请用 python3.11 或 python3.12 执行 setup。")
    if not sys.platform.startswith("linux"):
        raise RuntimeError("团队脚本面向 Linux/WSL；Windows 请进入 WSL Ubuntu 后运行。")
    for binary in ("node", "npm"):
        if shutil.which(binary) is None:
            raise RuntimeError(f"缺少 {binary}；请安装 Node.js 22 LTS（至少 22.12）并重新打开终端。")
    node = subprocess.check_output(["node", "--version"], text=True).strip()
    if not node_supported(node):
        raise RuntimeError(f"Node {node} 不满足 Vite 要求；推荐 Node.js 22 LTS，至少 22.12。")
    libc, version = platform.libc_ver()
    numbers = tuple(map(int, re.findall(r"\d+", version)[:2]))
    needs_cargo = platform.machine().lower() not in {"x86_64", "amd64"} or libc != "glibc" or numbers < (2, 39)
    if needs_cargo and shutil.which("cargo") is None:
        raise RuntimeError("当前 Linux 需要编译 ripgrep 依赖；先安装稳定版 Rust/Cargo（https://rustup.rs）。")
    if not (FRONTEND / "package-lock.json").is_file():
        raise RuntimeError("缺少前端 package-lock.json；请拉取完整团队仓库，npm ci 需要锁文件。")
    if shutil.which("bwrap") is None:
        print("提示：未安装 bubblewrap；产品 MCP 查询/报价可用，受限 bash 工具需 sudo apt install bubblewrap。")
    print(f"Python {platform.python_version()} / Node {node}")


def setup(args, env: dict[str, str]) -> None:
    if not args.dry_run:
        prerequisite_check()
    if not PYTHON.exists():
        run([sys.executable, "-m", "venv", VENV], env=env, dry_run=args.dry_run)
    elif not args.dry_run:
        run([PYTHON, "-c", "import sys; assert sys.version_info >= (3, 11), '请使用 Python 3.11+ 重建 .venv'"], env=env)
    run([PYTHON, "-m", "pip", "install", "--upgrade", "pip"], env=env, dry_run=args.dry_run)
    run([PYTHON, "-m", "pip", "install", "-r", ROOT / "requirements.txt"], env=env, dry_run=args.dry_run)
    run([PYTHON, "-m", "pip", "install", "--no-deps", "-e", ROOT], env=env, dry_run=args.dry_run)
    run(["npm", "--prefix", FRONTEND, "ci", "--no-audit", "--no-fund"], env=env, dry_run=args.dry_run)
    build_env = dict(env, VITE_EDITION="ce", VITE_DEFAULT_LANGUAGE="zh-CN")
    if "--max-old-space-size=" not in build_env.get("NODE_OPTIONS", ""):
        build_env["NODE_OPTIONS"] = (build_env.get("NODE_OPTIONS", "") + " --max-old-space-size=6144").strip()
    run(["npm", "--prefix", FRONTEND, "run", "build"], env=build_env, dry_run=args.dry_run)
    print("依赖和前端准备完成。首次部署执行 team.py init；已有账号执行 team.py install --username YOUR_USERNAME 更新外贸业务助手。")


def initialize(home: Path, username: str | None, *, port: int = 3001, legacy_chat_completions: bool = False, repair_legacy_filenames: bool = False, expected_filename_repairs: int | None = None) -> str:
    # No password flags or environment input: enter the password only in a TTY.
    from foreign_trade.upgrade import prepare_database
    prepare_database(home, allow_create=True, legacy_chat_completions=legacy_chat_completions, repair_legacy_filenames=repair_legacy_filenames, expected_filename_repairs=expected_filename_repairs)
    os.environ.update(runtime_env(home, port))
    from cli import apply_local_env, bootstrap_admin, mark_web_onboarding_complete
    apply_local_env(port)
    from core.db.engine import SessionLocal
    from core.db.models import UserShadow
    from core.files.content.branding import seed_page_config_if_missing, enforce_ce_branding
    from core.llm import prompt_versions as prompt_version_service

    username = username or input("本机登录用户名 [admin]: ").strip() or "admin"
    with SessionLocal() as db:
        existing = db.query(UserShadow.user_id).filter(UserShadow.username == username).one_or_none()
        has_account = db.query(UserShadow.user_id).first() is not None
    if existing:
        print("该本机账号已存在；保留密码与权限，继续安装/更新外贸演示内容。")
    else:
        if has_account:
            raise RuntimeError("数据目录已有账号。请使用已有用户名运行 init/install；新账号请在网页账号管理中创建。")
        if not sys.stdin.isatty():
            raise RuntimeError("首次创建账号需交互终端；请在 WSL 终端执行 init，密码不通过参数或文件传入。")
        password = getpass.getpass("本机登录密码: ")
        if password != getpass.getpass("确认密码: "):
            raise RuntimeError("两次密码不一致；未创建账号。")
        user_id = bootstrap_admin(username, password)
        del password
        mark_web_onboarding_complete(user_id)
        print("本机管理员账号已创建。")
    with SessionLocal() as db:
        seed_page_config_if_missing(db)
        enforce_ce_branding(db)
        prompt_version_service.seed_from_filesystem(db=db)
    return username


def install(home: Path, username: str, env: dict[str, str], dry_run: bool, *, legacy_chat_completions: bool = False, repair_legacy_filenames: bool = False, expected_filename_repairs: int | None = None) -> None:
    command = [PYTHON, HERE / "install.py", "--app-home", home, "--username", username, "--port", env.get("BACKEND_PORT", "3001"),
         "--apply-homepage-copy", "--apply-assistant-prompt"]
    if legacy_chat_completions:
        command.append("--legacy-chat-completions")
    if repair_legacy_filenames:
        command.append("--repair-legacy-filenames")
    if expected_filename_repairs is not None:
        command.extend(["--expected-filename-repairs", str(expected_filename_repairs)])
    run(command, env=env, dry_run=dry_run)


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def start(args, home: Path, env: dict[str, str]) -> None:
    web_port = getattr(args, "port", 3001)
    if not args.dry_run:
        if not (home / "data.db").is_file():
            raise RuntimeError("先执行 init 创建本机账号并安装演示插件。")
        if not (FRONTEND / "dist/index.html").is_file():
            raise RuntimeError("前端尚未构建；先执行 setup。")
        if web_port in (8900, 9120):
            raise RuntimeError("网页端口不能与本机沙箱 8900 或外贸 MCP 9120 相同。")
        for port in (web_port, 8900):
            if port_open(port):
                raise RuntimeError(f"端口 {port} 已被占用；不会停止或接管现有服务。请先结束原来的本机实例。")
        if port_open(9120):
            pid_file = HERE / ".runtime/server.pid"
            try:
                proc = Path("/proc") / str(int(pid_file.read_text().strip()))
                owned = (proc / "cwd").resolve() == HERE and str(HERE / "mcp_server.py").encode() in (proc / "cmdline").read_bytes().split(b"\0")
            except (OSError, ValueError):
                owned = False
            if not owned:
                raise RuntimeError("端口 9120 已被其他实例占用；不会接管它。")
    run([PYTHON, HERE / "manage.py", "start"], env=env, dry_run=args.dry_run)
    print(f"打开 http://127.0.0.1:{web_port}，用自己的账号登录。首次在 设置→模型服务 添加支持工具调用的模型并指派 main_agent。")
    print("对话中可选择“外贸业务助手（演示）”处理询盘和商品资料；三处工作台保留，用于查看、编辑与人工验收同一业务记录。")
    print("保持此终端运行，Ctrl-C 停止网页后端；MCP 单独停止：.venv/bin/python extensions/foreign_trade/manage.py stop")
    command = [str(VENV / "bin/hugagent-server"), "serve", "--host", "127.0.0.1", "--port", str(web_port), "--no-browser"]
    if args.dry_run:
        run(command, env=env, dry_run=True)
    else:
        # Replace this process so Ctrl-C reaches the actual foreground server.
        os.chdir(ROOT)
        os.execve(command[0], command, env)


def check(args, env: dict[str, str]) -> None:
    web_port = getattr(args, "port", 3001)
    # Deliberately enumerate unittest suites: the similarly named collaboration
    # module uses pytest fixtures and must not be imported or silently skipped.
    for filename in (
        "test_foreign_trade_engine.py",
        "test_foreign_trade_env_isolation.py",
        "test_foreign_trade_quote_identity.py",
        "test_foreign_trade_quote_presentation.py",
        "test_foreign_trade_team.py",
    ):
        run([PYTHON, "-m", "unittest", "discover", "-s", ROOT / "tests", "-p", filename],
            env=env, dry_run=args.dry_run)
    frontend_env = dict(env, FOREIGN_TRADE_TEST_PYTHON=str(PYTHON))
    for script in (
        "test:foreign-trade-quote",
        "test:foreign-trade-content-card",
        "test:foreign-trade-collaboration",
        "test:foreign-trade-content-mode",
    ):
        run(["npm", "--prefix", FRONTEND, "run", script],
            env=frontend_env, dry_run=args.dry_run)
    print("快速离线自检完成：unittest 与前端报价、资料、协同和生成模式检查；未运行完整 pytest、真实模型对话或完整工作台验收。")
    if args.running:
        run([PYTHON, HERE / "smoke_test.py"], env=env, dry_run=args.dry_run)
        if not args.dry_run:
            import urllib.request
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{web_port}/", timeout=5) as response:
                if response.status != 200 or "<html" not in response.read().decode("utf-8").lower():
                    raise RuntimeError("网页服务没有返回 HTML。")
        print(f"本机网页 http://127.0.0.1:{web_port}/ 与 MCP 检查完成；模型对话、工具调用和文件下载仍需在网页实际验收。")


def web_port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("网页端口必须为 1—65535 的整数") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("网页端口必须为 1—65535 的整数")
    return port


def main(argv: list[str] | None = None) -> int:
    global VENV, PYTHON
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("setup", "init", "install", "upgrade", "start", "check"))
    parser.add_argument("--app-home", type=Path, default=DEFAULT_HOME, help="独立数据目录，默认 ~/.foreign-trade-agent；不继承 HUGAGENT_HOME")
    parser.add_argument("--port", type=web_port_number, default=3001, help="网页/API 端口，默认 3001；冲突时可显式使用 3002，不停止占用者")
    parser.add_argument("--venv", type=Path, help="显式选择虚拟环境，默认项目 .venv")
    parser.add_argument("--legacy-chat-completions", action="store_true", help="显式确认既有无版本本地库来自旧Chat Completions运行时")
    parser.add_argument("--repair-legacy-filenames", action="store_true", help="以元数据重命名保留旧同名文件，保留修复审计与回滚快照")
    parser.add_argument("--expected-filename-repairs", type=int, help="修复数量与核对值不一致时停止")
    parser.add_argument("--restore", type=Path, help="仅 upgrade：从本数据目录内的备份恢复，先保留恢复前快照")
    parser.add_argument("--username", help="本机已有账号；首次 init 可交互输入")
    parser.add_argument("--dry-run", action="store_true", help="仅展示步骤，不安装依赖、不创建账号或数据、不启动服务")
    parser.add_argument("--running", action="store_true", help="check 时额外验证已启动的网页与 MCP（不调用付费模型）")
    args = parser.parse_args(argv)
    if args.venv is not None:
        VENV = args.venv.expanduser().resolve()
        PYTHON = VENV / "bin/python"
    home = args.app_home.expanduser().resolve()
    env = runtime_env(home, args.port)
    print("公开源码：" + str(ROOT))
    print("本机数据：" + str(home))
    try:
        if args.restore and args.action != "upgrade":
            raise RuntimeError("--restore 仅用于 upgrade；恢复前须停止该数据目录的后端。")
        if args.action != "setup" and not args.dry_run:
            if not PYTHON.is_file():
                raise RuntimeError("尚未建立 .venv；请先运行 setup。")
            if Path(sys.prefix).resolve() != VENV.resolve():
                os.execve(str(PYTHON), [str(PYTHON), str(Path(__file__).resolve()), *(argv if argv is not None else sys.argv[1:])], env)
        if args.action == "setup":
            setup(args, env)
        elif args.action == "upgrade":
            command = [PYTHON, HERE / "upgrade.py", "--app-home", home]
            if args.restore:
                command.extend(["--restore", args.restore])
            if args.legacy_chat_completions:
                command.append("--legacy-chat-completions")
            if args.repair_legacy_filenames:
                command.append("--repair-legacy-filenames")
            if args.expected_filename_repairs is not None:
                command.extend(["--expected-filename-repairs", str(args.expected_filename_repairs)])
            run(command, env=env, dry_run=args.dry_run)
        elif args.action in ("init", "install"):
            if args.action == "init":
                if args.dry_run:
                    print("[dry-run] 交互创建本机账号（已有账号保留密码和权限），初始化页面与提示词。")
                    username = args.username or "YOUR_LOCAL_USERNAME"
                else:
                    os.environ.update(env)
                    username = initialize(home, args.username, port=args.port, legacy_chat_completions=args.legacy_chat_completions, repair_legacy_filenames=args.repair_legacy_filenames, expected_filename_repairs=args.expected_filename_repairs)
            else:
                username = args.username
                if not username:
                    raise RuntimeError("install 需要 --username 指定已创建的本机账号。")
            install(home, username, env, args.dry_run, legacy_chat_completions=args.legacy_chat_completions, repair_legacy_filenames=args.repair_legacy_filenames, expected_filename_repairs=None if args.action == "init" else args.expected_filename_repairs)
            print(f"下一步：.venv/bin/python extensions/foreign_trade/team.py start --port {args.port}（自定义数据目录/环境时继续带 --app-home/--venv）。")
        elif args.action == "start":
            start(args, home, env)
        else:
            check(args, env)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print("失败：" + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
