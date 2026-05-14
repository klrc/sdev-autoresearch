#!/bin/bash

# sdev → PyPI：python3 -m build + twine upload
#
# 版本号来源（二选一）：
#   - 导出 SDEV_RELEASE_VERSION=1.2.3（推荐 CI / 非版本分支一键发版）
#   - 或未设置 SDEV_RELEASE_VERSION 时：当前 git 分支名必须为 x.y.z（与原先一致）
#
# 密钥（二选一，勿入库）：
#   - export PYPI_API_TOKEN=pypi-xxxx
#   - 或在本目录放置 api_key 单行 token
#
# 依赖（本机自备，脚本不创建 venv）：python3 -m build、twine
# 发布后的 pip 校验默认使用官方 Simple（https://pypi.org/simple），避免镜像未同步；可通过 SDEV_PYPI_SIMPLE 改写

set -e
_SDEV_TMPDIR=""
_on_exit() {
  rm -rf "$_SDEV_TMPDIR" 2>/dev/null || true
  unset TWINE_USERNAME TWINE_PASSWORD TWINE_NON_INTERACTIVE 2>/dev/null || true
}
trap _on_exit EXIT

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

if ! command -v git &>/dev/null; then error "git 未安装"; exit 1; fi
if ! command -v python3 &>/dev/null; then error "python3 未安装"; exit 1; fi
if ! python3 -m build --help &>/dev/null; then
  error "无法执行 python3 -m build，请先安装 build（pipx install build 等）"
  exit 1
fi
if ! command -v twine &>/dev/null; then
  error "未找到 twine（pipx install twine 等）"
  exit 1
fi

ver_re='^[0-9]+\.[0-9]+\.[0-9]+$'
if [[ -n "${SDEV_RELEASE_VERSION:-}" ]]; then
  version="${SDEV_RELEASE_VERSION}"
  if [[ ! "$version" =~ $ver_re ]]; then
    error "SDEV_RELEASE_VERSION='$version' 必须为 x.y.z"
    exit 1
  fi
  info "使用环境变量版本: $version"
else
  branch=$(git branch --show-current)
  if [[ ! "$branch" =~ $ver_re ]]; then
    error "当前分支 '$branch' 不是 x.y.z；或请设置 SDEV_RELEASE_VERSION=x.y.z"
    exit 1
  fi
  version="$branch"
  info "使用分支名为版本: $version"
fi

sed -i "s/^version = \"[^\"]*\"/version = \"$version\"/" pyproject.toml
sed -i "s/^__version__ = \"[^\"]*\"/__version__ = \"$version\"/" sdev/__init__.py
success "版本号已写入 pyproject.toml 与 sdev/__init__.py → $version"

rm -rf build/ dist/ *.egg-info/ sdev.egg-info/
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

info "构建 (python3 -m build)..."
python3 -m build
success "构建完成"

if [[ -n "${PYPI_API_TOKEN:-}" ]]; then
  api_key="$PYPI_API_TOKEN"
elif [[ -f "api_key" ]]; then
  api_key=$(tr -d ' \t\r\n' < api_key)
else
  error "缺少凭证：设置环境变量 PYPI_API_TOKEN 或在本目录创建 api_key 文件"
  exit 1
fi
if [[ -z "$api_key" ]]; then error "凭证为空"; exit 1; fi

export TWINE_USERNAME="__token__"
export TWINE_PASSWORD="$api_key"
export TWINE_NON_INTERACTIVE=1
info "上传到 PyPI (twine upload)..."
twine upload dist/*

info "等待 PyPI 索引更新并在 JSON API 确认版本..."
MAX_RETRIES=15
RETRY_INTERVAL=10
ok=false
for ((i=1; i<=MAX_RETRIES; i++)); do
  if curl -fsS -o /dev/null "https://pypi.org/pypi/sdev/${version}/json"; then
    success "PyPI JSON 已可查询: sdev==${version}"
    ok=true
    break
  fi
  warning "第 $i 次查询暂无该版本，${RETRY_INTERVAL}s 后重试…"
  sleep "$RETRY_INTERVAL"
done

if [[ "$ok" != true ]]; then
  error "未及时在索引中看到 ${version}，请到 https://pypi.org/project/sdev/${version}/ 人工确认"
  exit 1
fi

_SDEV_TMPDIR=$(mktemp -d)

# 校验时必须走官方 Simple，否则会受本机镜像（如同步延迟）影响
_PYPI_SIMPLE="${SDEV_PYPI_SIMPLE:-https://pypi.org/simple}"

info "校验：从官方索引安装（${_PYPI_SIMPLE}）到临时目录并核对 __version__…"
python3 -m pip install -q --no-cache-dir --no-deps -t "$_SDEV_TMPDIR" \
  --index-url "$_PYPI_SIMPLE" \
  "sdev==${version}"
got=$(PYTHONPATH="$_SDEV_TMPDIR" python3 -c "import sdev; print(sdev.__version__)")
if [[ "$got" != "$version" ]]; then
  error "安装后 __version__ 为 '$got'，期望 '$version'"
  exit 1
fi
success "已从 PyPI 安装并校验 __version__ == ${version}"

success "发布并校验完成: pip install \"sdev==${version}\""
