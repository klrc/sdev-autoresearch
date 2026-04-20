#!/bin/bash

# sdev 自动构建并上传到 PyPI（与 /nfs/projects/sdev 流程一致，仅 pyproject.toml，无 setup.py）
# 1. 从 git 分支名获取版本号（须为 x.y.z）
# 2. 更新 pyproject.toml、sdev/__init__.py 中的版本
# 3. 清理、构建、用 api_key 文件中的 token 上传
# 发布前：git checkout -b 1.0.0 && 本脚本；上传后可将版本合并回 main 并打 tag v1.0.0

set -e

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
if ! command -v python &>/dev/null; then error "python 未安装"; exit 1; fi
if ! python -c "import build" &>/dev/null; then info "安装 build..."; pip install build; fi
if ! python -c "import twine" &>/dev/null; then info "安装 twine..."; pip install twine; fi

branch=$(git branch --show-current)
if [[ ! "$branch" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then error "分支名 '$branch' 必须为 x.y.z 版本号格式"; exit 1; fi
version=$branch
info "当前版本: $version"

sed -i "s/^version = \"[^\"]*\"/version = \"$version\"/" pyproject.toml
sed -i "s/^__version__ = \"[^\"]*\"/__version__ = \"$version\"/" sdev/__init__.py
success "版本号已更新为 $version"

rm -rf build/ dist/ *.egg-info/ sdev.egg-info/
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
success "清理完成"

info "开始构建..."
python -m build
success "构建完成"

if [[ ! -f "api_key" ]]; then error "api_key 文件不存在"; exit 1; fi
api_key=$(cat api_key)
if [[ -z "$api_key" ]]; then error "api_key 文件为空"; exit 1; fi
success "API 密钥检查通过"

export TWINE_USERNAME="__token__"
export TWINE_PASSWORD="$api_key"
export TWINE_DISABLE_PROMPT=1
info "上传到 PyPI..."
twine upload dist/*
if [[ $? -eq 0 ]]; then
  success "上传成功"
else
  error "上传失败"
  exit 1
fi
unset TWINE_USERNAME TWINE_PASSWORD TWINE_DISABLE_PROMPT

info "等待 PyPI 索引更新并验证安装..."
MAX_RETRIES=10
RETRY_INTERVAL=10
installed_success=false

for ((i=1; i<=MAX_RETRIES; i++)); do
  if pip install --no-cache-dir "sdev==$version" --index-url https://pypi.org/simple &>/dev/null; then
    current_installed=$(python -c "import sdev; print(sdev.__version__)")
    if [[ "$current_installed" == "$version" ]]; then
      success "PyPI 安装验证通过: 已正确安装版本 $version"
      installed_success=true
      break
    fi
  fi
  warning "尝试第 $i 次验证失败，可能是 PyPI 还没更新，${RETRY_INTERVAL}秒后重试..."
  sleep $RETRY_INTERVAL
done

if [ "$installed_success" = false ]; then
  error "PyPI 安装验证失败：在尝试了 $((MAX_RETRIES * RETRY_INTERVAL)) 秒后仍未检测到新版本 $version。上传可能已成功，请稍后手动运行 'pip install -U sdev' 验证。"
  exit 1
fi

success "全部流程完成！版本 $version 已发布。"
