# 使用 VSCode 克隆并开发 GitHub 项目（以 all_codegen 为例）

## 前置条件

1. **已安装 [Git](https://git-scm.com/downloads)**
   - 可在终端输入 `git --version` 检查是否安装。
2. **已安装 [Visual Studio Code](https://code.visualstudio.com/)**
3. （可选）安装 [VSCode GitHub 扩展](https://marketplace.visualstudio.com/items?itemName=GitHub.vscode-pull-request-github)

------

## 步骤一：复制仓库地址

1. 打开你的项目地址 https://github.com/chokkint/all_codegen

2. 点击右上角绿色的 `Code` 按钮，选择 `HTTPS` 方式，复制仓库链接：

   ```
   https://github.com/chokkint/all_codegen.git
   ```

------

## 步骤二：通过 VSCode 克隆项目到本地

### 方法1：使用 VSCode 图形界面

1. 打开 VSCode。
2. 在欢迎页面点击 `Clone Git Repository...`，或通过菜单栏选择：
   `View` → `Command Palette...`（快捷键 Ctrl+Shift+P），输入并选择：`Git: Clone`
3. 粘贴你的仓库地址 `https://github.com/chokkint/all_codegen.git`，回车。
4. 选择一个本地文件夹作为代码存储位置。
5. VSCode 会自动下载代码并提示“是否打开该项目”，选择 `Open` 或 `打开`。

### 方法2：使用命令行克隆

1. 打开终端（Terminal），cd 到你想存放代码的目录。

2. 执行：

   ```sh
   git clone https://github.com/chokkint/all_codegen.git
   ```

3. 克隆后，用 VSCode 打开本地项目目录即可。

------

## 步骤三：在 VSCode 进行开发

1. 使用 VSCode 打开本地 `all_codegen` 文件夹。
2. 可以直接编辑、运行、调试代码。
3. 建议配置好 Python 虚拟环境，并安装项目需要的依赖包（如 `requirements.txt`）。

### 创建并激活 Python 虚拟环境（推荐）

```sh
# 进入项目根目录
cd all_codegen

# 创建虚拟环境（推荐用 venv）
python3 -m venv venv

# macOS/Linux 激活
source venv/bin/activate

# Windows 激活
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

------

## 步骤四：日常开发与代码同步

- **查看代码状态**：点击 VSCode 左侧的“源代码管理”图标。
- **提交改动（commit）**：写好注释后，点击 √ 或使用 Command Palette 选择 Git: Commit。
- **推送到 GitHub（push）**：点击“↑”按钮或 Command Palette 执行 Git: Push。
- **拉取最新代码（pull）**：点击“↓”按钮或执行 Git: Pull。

------

## 常见问题

- **需要登录 GitHub**
  首次 push 或 clone 私有仓库时，可能需要输入 GitHub 用户名和 [Personal Access Token](https://github.com/settings/tokens)。
- **.gitignore 文件**
  修改 `.gitignore` 可以避免无关文件（如 venv、output）上传。
- **分支开发**
  可通过 VSCode 左下角分支图标切换、创建新分支。

------

## 参考

- [VSCode 官方 Git 教程（中文）](https://code.visualstudio.com/docs/editor/versioncontrol)
- [GitHub 克隆仓库帮助](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository)

